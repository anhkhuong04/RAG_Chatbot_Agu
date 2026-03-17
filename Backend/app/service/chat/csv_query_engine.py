"""
CSV Query Engine module.

Manages PandasQueryEngine instances for structured CSV data (điểm chuẩn, học phí).
Handles engine initialization, query execution (sync + stream), validation, and retry.

Extracted from ChatService Pandas-related methods (lines 1080-1565).
"""
import os
import re
import glob
import logging
import asyncio
from typing import Optional, List, AsyncGenerator

import pandas as pd
from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole

from app.service.prompts import RAG_SYSTEM_PROMPT

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)

logger = logging.getLogger(__name__)

# PandasQueryEngine (optional — requires llama-index-experimental)
try:
    from llama_index.experimental.query_engine import PandasQueryEngine

    HAS_PANDAS_ENGINE = True
except ImportError:
    HAS_PANDAS_ENGINE = False
    logger.warning("llama-index-experimental not installed. PandasQueryEngine unavailable.")


class CSVQueryEngine:
    """Manages PandasQueryEngines for structured CSV data."""

    def __init__(self, structured_dir: str, get_intent_prompt_fn=None):
        self.structured_dir = structured_dir
        self._get_intent_prompt = get_intent_prompt_fn or (lambda _: "")

        self._diem_chuan_engine = None
        self._hoc_phi_engine = None
        self._latest_diem_chuan_year: int | None = self.detect_latest_year("diem_chuan")
        self._latest_hoc_phi_year: int | None = self.detect_latest_year("hoc_phi")

        # Initialize engines
        self.init_engines()

        # Startup diagnostics
        if self._diem_chuan_engine:
            print("✅ PandasQueryEngine [Điểm chuẩn] sẵn sàng")
        else:
            print("⚠️ PandasQueryEngine [Điểm chuẩn] KHÔNG khả dụng — câu hỏi điểm chuẩn sẽ fallback sang RAG")
        if self._hoc_phi_engine:
            print("✅ PandasQueryEngine [Học phí] sẵn sàng")
        else:
            print("⚠️ PandasQueryEngine [Học phí] KHÔNG khả dụng — câu hỏi học phí sẽ fallback sang RAG")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def diem_chuan_engine(self):
        return self._diem_chuan_engine

    @property
    def hoc_phi_engine(self):
        return self._hoc_phi_engine

    @property
    def latest_diem_chuan_year(self) -> int | None:
        return self._latest_diem_chuan_year

    @property
    def latest_hoc_phi_year(self) -> int | None:
        return self._latest_hoc_phi_year

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def detect_latest_year(self, prefix: str) -> int | None:
        pattern = os.path.join(self.structured_dir, f"{prefix}_*.csv")
        csv_files = glob.glob(pattern)
        years = []
        for f in csv_files:
            # Match formats like diem_chuan_2025.csv or hoc_phi_dhag_25_26.csv
            match = re.search(r"(\d{4}|\d{2}_\d{2})", os.path.basename(f))
            if match:
                year_str = match.group(1)
                if "_" in year_str:
                    # e.g., '25_26' -> 2025
                    year_val = int("20" + year_str.split("_")[0])
                else:
                    year_val = int(year_str)
                years.append(year_val)
        return max(years) if years else None

    def init_engines(self, year: int | None = None):
        if not HAS_PANDAS_ENGINE:
            logger.warning("PandasQueryEngine not available. Skipping CSV engine init.")
            return

        if not os.path.isdir(self.structured_dir):
            logger.info(f"Structured data dir not found: {self.structured_dir}")
            return

        # --- 1. ENGINE ĐIỂM CHUẨN ---
        dc_year = year or self.detect_latest_year("diem_chuan")
        if dc_year:
            diem_chuan_meta = self._read_metadata_file(f"diem_chuan_{dc_year}_metadata.txt")
            self._diem_chuan_engine = self._load_csv_engine(
                self.structured_dir,
                "diem_chuan",
                "Dữ liệu điểm chuẩn tuyển sinh Đại học An Giang",
                dynamic_notes=diem_chuan_meta,
            )
            logger.info(f"📊 Điểm chuẩn engine initialized for year {dc_year}")
        else:
            logger.info("📊 No điểm chuẩn CSV files found — skipping engine init")

        # --- 2. ENGINE HỌC PHÍ ---
        hp_year = year or self.detect_latest_year("hoc_phi")
        hoc_phi_meta = ""
        if hp_year:
            hoc_phi_meta = self._read_metadata_file(f"hoc_phi_{hp_year}_metadata.txt")
        if not hoc_phi_meta:
            meta_pattern = os.path.join(self.structured_dir, "hoc_phi_*_metadata.txt")
            meta_files = sorted(glob.glob(meta_pattern), reverse=True)
            if meta_files:
                hoc_phi_meta = self._read_metadata_file(os.path.basename(meta_files[0]))

        self._hoc_phi_engine = self._load_multi_csv_engine(
            self.structured_dir,
            "hoc_phi",
            "Dữ liệu học phí Đại học An Giang",
            dynamic_notes=hoc_phi_meta,
        )
        if self._hoc_phi_engine:
            logger.info(f"📊 Học phí engine initialized (year={hp_year or 'auto'})")
        else:
            logger.info("📊 No học phí CSV files found — skipping engine init")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_metadata_file(self, filename: str) -> str:
        filepath = os.path.join(self.structured_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                logger.info(f"📝 Loaded dynamic metadata from {filename} ({len(content)} chars)")
                return content
        logger.info(f"📝 No metadata file found: {filename}")
        return ""

    def _load_csv_engine(
        self, directory: str, prefix: str, description: str, dynamic_notes: str = ""
    ):
        try:
            pattern = os.path.join(directory, f"{prefix}_*.csv")
            csv_files = sorted(glob.glob(pattern), reverse=True)

            if not csv_files:
                logger.info(f"No CSV files found for prefix: {prefix}")
                return None

            latest_csv = csv_files[0]
            df = pd.read_csv(latest_csv, encoding="utf-8-sig")

            if df.empty:
                logger.warning(f"Empty CSV file: {latest_csv}")
                return None

            instruction_str = self._build_instruction(df, description, dynamic_notes)

            engine = PandasQueryEngine(
                df=df,
                verbose=True,
                synthesize_response=False,
                instruction_str=instruction_str,
            )

            columns_str = ", ".join(df.columns.tolist())
            logger.info(
                f"📊 Loaded PandasQueryEngine from {latest_csv} "
                f"({len(df)} rows, cols={columns_str}, metadata={'yes' if dynamic_notes else 'no'})"
            )
            print(
                f"📊 Loaded PandasQueryEngine from {latest_csv} "
                f"({len(df)} rows, metadata={'yes' if dynamic_notes else 'no'})"
            )
            return engine

        except Exception as e:
            logger.error(f"❌ Failed to load CSV engine for {prefix}: {e}")
            print(f"❌ Failed to load CSV engine for {prefix}: {e}")
            return None

    def _load_multi_csv_engine(
        self, directory: str, prefix: str, description: str, dynamic_notes: str = ""
    ):
        try:
            pattern = os.path.join(directory, f"{prefix}_*.csv")
            csv_files = sorted(glob.glob(pattern))

            if not csv_files:
                logger.info(f"No CSV files found for prefix: {prefix}")
                return None

            if len(csv_files) == 1:
                return self._load_csv_engine(directory, prefix, description, dynamic_notes=dynamic_notes)

            frames = []
            for csv_path in csv_files:
                try:
                    df = pd.read_csv(csv_path, encoding="utf-8-sig")
                    if not df.empty:
                        basename = os.path.basename(csv_path).replace(".csv", "")
                        df["bang"] = basename
                        frames.append(df)
                        logger.info(f"📊 Loaded {len(df)} rows from {csv_path}")
                except Exception as e:
                    logger.warning(f"Could not load {csv_path}: {e}")

            if not frames:
                return None

            merged_df = pd.concat(frames, ignore_index=True)

            instruction_str = self._build_instruction(
                merged_df,
                description,
                dynamic_notes,
                extra_schema_note=f"DataFrame 'df' có {len(merged_df)} dòng (merged từ {len(frames)} bảng).\nCột 'bang' cho biết dòng thuộc bảng nào.\n",
            )

            engine = PandasQueryEngine(
                df=merged_df,
                verbose=True,
                synthesize_response=False,
                instruction_str=instruction_str,
            )

            logger.info(
                f"📊 Loaded multi-CSV PandasQueryEngine for {prefix} "
                f"({len(merged_df)} total rows from {len(frames)} files, "
                f"metadata={'yes' if dynamic_notes else 'no'})"
            )
            print(
                f"📊 Loaded multi-CSV PandasQueryEngine for {prefix} "
                f"({len(merged_df)} total rows from {len(frames)} files, "
                f"metadata={'yes' if dynamic_notes else 'no'})"
            )
            return engine

        except Exception as e:
            logger.error(f"❌ Failed to load multi-CSV engine for {prefix}: {e}")
            print(f"❌ Failed to load multi-CSV engine for {prefix}: {e}")
            return None

    @staticmethod
    def _build_instruction(
        df: pd.DataFrame,
        description: str,
        dynamic_notes: str = "",
        extra_schema_note: str = "",
    ) -> str:
        columns_str = ", ".join(df.columns.tolist())
        notes_section = ""
        if dynamic_notes:
            notes_section = (
                f"--- CHÚ THÍCH & TỪ ĐIỂN DỮ LIỆU (trích từ tài liệu gốc) ---\n"
                f"{dynamic_notes}\n\n"
            )

        schema_line = extra_schema_note or f"DataFrame 'df' có {len(df)} dòng với các cột: [{columns_str}]\n"
        if extra_schema_note:
            schema_line += f"Các cột: [{columns_str}]\n"

        return (
            f"Bạn là chuyên gia phân tích dữ liệu tuyển sinh. "
            f"Hãy viết code Pandas (df) để tìm câu trả lời chính xác.\n\n"
            f"{notes_section}"
            f"--- DYNAMIC SCHEMA ---\n"
            f"{schema_line}"
            f"Mô tả: {description}\n\n"
            f"--- SAMPLE DATA (5 dòng đầu) ---\n"
            f"{df.head().to_string(index=False)}\n\n"
            f"QUAN TRỌNG: Output CHỈ là raw executable Python code.\n"
            f"KHÔNG được bọc code trong markdown code blocks (``` hoặc ```python).\n"
            f"KHÔNG thêm giải thích hay comment. CHỈ code thuần.\n"
            f"Biến DataFrame tên là 'df'.\n"
            f"KHÔNG dùng print(). Output PHẢI là MỘT BIỂU THỨC Pandas duy nhất có thể eval trực tiếp (ví dụ: df[df['NganhHoc'].str.contains('Công nghệ thông tin', case=False, na=False)]).\n"
            f"TUYỆT ĐỐI KHÔNG dùng phép gán biến (KHÔNG viết 'result = ...'), KHÔNG gọi to_markdown()/to_string(), và KHÔNG dùng .head() để giới hạn dữ liệu.\n"
            f"Khi dùng str.contains(), LUÔN thêm na=False để tránh lỗi NaN.\n"
            f"Khi tìm ngành theo tên, LUÔN dùng str.contains(case=False, na=False) thay vì == để tránh miss do viết hoa/thường.\n"
            f"Khi cần tìm theo mã ngành (số), ép kiểu str trước khi so sánh: df[df['MaNganh'].astype(str).str.contains('7480201')].\n"
            f"Trả về TẤT CẢ các dòng khớp, KHÔNG giới hạn số kết quả.\n"
            f"\n--- NGUYÊN TẮC BẮT BUỘC VỀ CỘT ---\n"
            f"TUYỆT ĐỐI KHÔNG được chọn chỉ một vài cột (VD: df[['col1','col2']]). "
            f"LUÔN trả về TẤT CẢ các cột của DataFrame sau khi filter hàng.\n"
            f"KHÔNG BAO GIỜ viết df[['col1','col2']], df.loc[:,['col1']], hay bất kỳ dạng column selection nào. "
            f"Chỉ được filter hàng (rows), KHÔNG filter cột (columns).\n"
            f"Khi cần tìm nhiều ngành cùng lúc, dùng toán tử | (OR): "
            f"df[df['NganhHoc'].str.contains('Ngành A|Ngành B', case=False, na=False)].\n"
            f"VÍ DỤ ĐÚNG: df[df['NganhHoc'].str.contains('Công nghệ thông tin', case=False, na=False)]\n"
            f"VÍ DỤ SAI (KHÔNG ĐƯỢC LÀM): df[df['NganhHoc'].str.contains('CNTT')][['MaNganh','PT2']]\n"
        )

    # ------------------------------------------------------------------
    # Validation & retry
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_pandas_output(raw_output: str, engine) -> bool:
        if not raw_output or raw_output in ("None", "", "none", "null"):
            return False

        try:
            df = engine._df if hasattr(engine, "_df") else None
            if df is None:
                return True

            expected_cols = set(df.columns.tolist())
            found_cols = sum(1 for col in expected_cols if col in raw_output)
            ratio = found_cols / len(expected_cols) if expected_cols else 1.0

            if ratio < 0.5:
                logger.warning(
                    f"⚠️ Pandas output missing columns: found {found_cols}/{len(expected_cols)} "
                    f"({ratio:.0%}). Output preview: {raw_output[:300]}..."
                )
                return False
            return True
        except Exception:
            return True

    @staticmethod
    async def _retry_pandas_query(engine, message: str) -> str | None:
        retry_message = (
            f"{message}\n\n"
            f"LƯU Ý ĐẶC BIỆT: Trả về TẤT CẢ các cột, KHÔNG chọn subset cột. "
            f"Code PHẢI là MỘT BIỂU THỨC Pandas duy nhất dạng: df[<điều_kiện_filter>]\n"
            f"TUYỆT ĐỐI KHÔNG dùng gán biến (KHÔNG 'result = ...') và KHÔNG gọi to_markdown/to_string."
        )
        try:
            # PandasQueryEngine internally uses signal-based timeout; it must run on main thread.
            pandas_response = engine.query(retry_message)
            raw_output = str(pandas_response)
            if raw_output in ("None", "", "none", "null"):
                meta = getattr(pandas_response, "metadata", {}) or {}
                raw_pandas = meta.get("raw_pandas_output")
                if raw_pandas is not None:
                    raw_output = str(raw_pandas)
            logger.info(f"[RETRY] Pandas retry result: {raw_output[:200]}...")
            return raw_output if raw_output not in ("None", "", "none", "null") else None
        except Exception as e:
            logger.warning(f"[RETRY] Pandas retry failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    async def handle_query(
        self, engine, message: str, source_label: str, intent: str = "general"
    ) -> tuple[str, List[str]]:
        try:
            # PandasQueryEngine internally uses signal-based timeout; it must run on main thread.
            pandas_response = engine.query(message)
            raw_output = str(pandas_response)

            if raw_output in ("None", "", "none", "null"):
                meta = getattr(pandas_response, "metadata", {}) or {}
                raw_pandas = meta.get("raw_pandas_output")
                if raw_pandas is not None:
                    raw_output = str(raw_pandas)
                    logger.info(f"[FIX] Recovered output from metadata: {raw_output[:200]}...")
                else:
                    logger.warning("Pandas query returned None with no metadata fallback")

            logger.info(f"Pandas query result ({source_label}): {raw_output[:500]}")

            if raw_output in ("None", "", "none", "null"):
                logger.warning("Pandas output is empty/None — returning None for fallback")
                return None, []  # Caller should fallback to RAG

            # Validate output completeness
            if not self._validate_pandas_output(raw_output, engine):
                logger.info("[RETRY] Output appears incomplete, retrying with explicit instruction...")
                retry_output = await self._retry_pandas_query(engine, message)
                if retry_output and self._validate_pandas_output(retry_output, engine):
                    raw_output = retry_output
                    logger.info("[RETRY] Retry succeeded with better output")
                else:
                    logger.info("[RETRY] Retry did not improve, using original output")

            intent_prompt = self._get_intent_prompt(intent)

            format_prompt = f"""{intent_prompt}

Dựa trên kết quả truy vấn từ {source_label}:

{raw_output}

Hãy format kết quả trên thành câu trả lời cho câu hỏi: "{message}"
- Sử dụng tiếng Việt
- Trình bày dạng bảng markdown theo cấu trúc đã quy định
- Giữ nguyên số liệu chính xác
- QUAN TRỌNG: BẮT BUỘC liệt kê ĐẦY ĐỦ tất cả các dòng dữ liệu có trong kết quả truy vấn. TUYỆT ĐỐI KHÔNG được cắt bớt, không được tóm tắt, và không dùng dấu '...'
- BẮT BUỘC giữ nguyên TẤT CẢ các cột dữ liệu có trong kết quả. KHÔNG được bỏ cột nào."""

            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=RAG_SYSTEM_PROMPT),
                ChatMessage(role=MessageRole.USER, content=format_prompt),
            ]

            response = await Settings.llm.achat(messages)
            return response.message.content, [f"Truy xuất từ {source_label}"]

        except Exception as e:
            logger.error(f"Pandas query error ({source_label}): {e}")
            return None, []  # Caller should fallback to RAG

    async def handle_query_stream(
        self, engine, message: str, source_label: str, intent: str = "general"
    ) -> AsyncGenerator[str, None]:
        try:
            # PandasQueryEngine internally uses signal-based timeout; it must run on main thread.
            pandas_response = engine.query(message)
            raw_output = str(pandas_response)

            if raw_output in ("None", "", "none", "null"):
                meta = getattr(pandas_response, "metadata", {}) or {}
                raw_pandas = meta.get("raw_pandas_output")
                if raw_pandas is not None:
                    raw_output = str(raw_pandas)
                    logger.info(f"[STREAM][FIX] Recovered output from metadata: {raw_output[:200]}...")
                else:
                    logger.warning("[STREAM] Pandas query returned None with no metadata fallback")

            logger.info(f"[STREAM] Pandas query result ({source_label}): {raw_output[:500]}")

            if raw_output in ("None", "", "none", "null"):
                logger.warning("[STREAM] Pandas output is empty/None")
                yield f"Không thể truy xuất dữ liệu từ {source_label}. Vui lòng thử lại."
                return

            # Validate output completeness
            if not self._validate_pandas_output(raw_output, engine):
                logger.info("[STREAM][RETRY] Output appears incomplete, retrying...")
                retry_output = await self._retry_pandas_query(engine, message)
                if retry_output and self._validate_pandas_output(retry_output, engine):
                    raw_output = retry_output
                    logger.info("[STREAM][RETRY] Retry succeeded with better output")
                else:
                    logger.info("[STREAM][RETRY] Retry did not improve, using original output")

            intent_prompt = self._get_intent_prompt(intent)

            format_prompt = f"""{intent_prompt}

Dựa trên kết quả truy vấn từ {source_label}:

{raw_output}

Hãy format kết quả trên thành câu trả lời cho câu hỏi: "{message}"
- Sử dụng tiếng Việt
- Trình bày dạng bảng markdown theo cấu trúc đã quy định
- Giữ nguyên số liệu chính xác
- QUAN TRỌNG: BẮT BUỘC liệt kê ĐẦY ĐỦ tất cả các dòng dữ liệu có trong kết quả truy vấn. TUYỆT ĐỐI KHÔNG được cắt bớt, không được tóm tắt, và không dùng dấu '...'
- BẮT BUỘC giữ nguyên TẤT CẢ các cột dữ liệu có trong kết quả. KHÔNG được bỏ cột nào."""

            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=RAG_SYSTEM_PROMPT),
                ChatMessage(role=MessageRole.USER, content=format_prompt),
            ]

            response_stream = await Settings.llm.astream_chat(messages)
            async for token in response_stream:
                yield token.delta

        except Exception as e:
            logger.error(f"[STREAM] Pandas query error ({source_label}): {e}")
            yield f"Không thể truy xuất dữ liệu từ {source_label}. Đang chuyển sang tìm kiếm thông thường..."

    def clear(self):
        self._diem_chuan_engine = None
        self._hoc_phi_engine = None
        self._latest_diem_chuan_year = self.detect_latest_year("diem_chuan")
        self._latest_hoc_phi_year = self.detect_latest_year("hoc_phi")
