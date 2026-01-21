"""
Query Transformation Pipeline for Advanced RAG
Bao gồm: Query Rewriting, Decomposition, Multi-Query Retrieval
"""
from typing import List, Dict, Any
from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM
from llama_index.core import Settings
import time
from app.core.logger import get_logger, LogContext
from app.core.metrics import track_rag_operation

logger = get_logger(__name__)

# ==========================================
# 1. QUERY REWRITING (Viết Lại Câu Hỏi)
# ==========================================

QUERY_REWRITE_PROMPT = PromptTemplate(
    """Bạn là chuyên gia tối ưu hóa câu hỏi tìm kiếm.

NHIỆM VỤ: Viết lại câu hỏi của người dùng thành dạng tối ưu để tìm kiếm thông tin trong cơ sở dữ liệu tuyển sinh đại học.

QUY TẮC:
1. Giữ nguyên ý nghĩa câu hỏi gốc
2. Chuẩn hóa thuật ngữ (VD: "điểm sàn" → "điểm chuẩn")
3. Làm rõ ngữ cảnh mơ hồ (VD: "năm nay" → "năm 2024")
4. Bổ sung từ khóa quan trọng nếu cần
5. Giữ ngắn gọn và tập trung

VÍ DỤ:
- Input: "điểm bao nhiêu vào được CNTT?"
  Output: "Điểm chuẩn ngành Công nghệ thông tin năm 2024"

- Input: "học phí mỗi năm khoảng bao nhiêu?"
  Output: "Học phí các ngành đào tạo theo năm học"

- Input: "có học bổng không?"
  Output: "Thông tin về học bổng và hỗ trợ tài chính cho sinh viên"

CÂU HỎI GỐC: {query_str}

VIẾT LẠI (chỉ trả về câu hỏi mới, không giải thích):"""
)

# ==========================================
# 2. QUERY DECOMPOSITION (Phân Rã Câu Hỏi)
# ==========================================

QUERY_DECOMPOSE_PROMPT = PromptTemplate(
    """Bạn là chuyên gia phân tích câu hỏi phức tạp.

NHIỆM VỤ: Phân tích câu hỏi và xác định xem có cần chia nhỏ thành các câu hỏi con hay không.

QUY TẮC:
1. NẾU câu hỏi đơn giản (1 chủ đề) → Trả về: "SIMPLE"
2. NẾU câu hỏi phức tạp (nhiều chủ đề) → Chia thành các câu hỏi con, mỗi câu trên 1 dòng

VÍ DỤ:
Input: "Điểm chuẩn ngành CNTT bao nhiêu?"
Output: SIMPLE

Input: "So sánh điểm chuẩn và học phí ngành CNTT với ngành Kinh tế"
Output:
Điểm chuẩn ngành Công nghệ thông tin
Học phí ngành Công nghệ thông tin
Điểm chuẩn ngành Kinh tế
Học phí ngành Kinh tế

Input: "Ngành nào có điểm chuẩn thấp nhất và học phí rẻ nhất?"
Output:
Ngành có điểm chuẩn thấp nhất
Ngành có học phí thấp nhất

CÂU HỎI: {query_str}

PHÂN TÍCH (nếu SIMPLE thì chỉ viết "SIMPLE", nếu phức tạp thì liệt kê từng câu hỏi con):"""
)

# ==========================================
# 3. MULTI-QUERY GENERATION (Tạo Câu Hỏi Đa Dạng)
# ==========================================

MULTI_QUERY_PROMPT = PromptTemplate(
    """Bạn là chuyên gia tạo các biến thể câu hỏi.

NHIỆM VỤ: Tạo 3 phiên bản khác nhau của câu hỏi gốc để tìm kiếm toàn diện hơn.

QUY TẮC:
1. Mỗi phiên bản phải diễn đạt khác nhau nhưng cùng ý nghĩa
2. Sử dụng từ đồng nghĩa và cách diễn đạt đa dạng
3. Mỗi câu hỏi trên 1 dòng
4. Không đánh số thứ tự

VÍ DỤ:
Input: "Điểm chuẩn ngành CNTT năm 2024"
Output:
Điểm chuẩn ngành Công nghệ thông tin năm 2024
Điểm trúng tuyển chuyên ngành CNTT năm 2024
Ngành Công nghệ thông tin cần bao nhiêu điểm để đậu năm 2024

CÂU HỎI GỐC: {query_str}

TẠO 3 BIẾN THỂ (mỗi câu 1 dòng):"""
)

# ==========================================
# 4. HyDE (Hypothetical Document Embeddings)
# ==========================================

HYDE_PROMPT = PromptTemplate(
    """Bạn là chuyên gia về tuyển sinh đại học.

NHIỆM VỤ: Viết một đoạn văn ngắn (2-3 câu) giả định trả lời câu hỏi này như thể bạn đang trích từ tài liệu chính thức.

LƯU Ý: 
- Không cần thông tin chính xác, chỉ cần phong cách và cấu trúc giống tài liệu thật
- Sử dụng thuật ngữ chuyên ngành
- Tập trung vào từ khóa và ngữ cảnh

VÍ DỤ:
Input: "Điểm chuẩn ngành CNTT năm 2024"
Output: "Theo quyết định của Hội đồng tuyển sinh, điểm chuẩn trúng tuyển ngành Công nghệ thông tin năm 2024 đối với phương thức xét tuyển dựa trên kết quả thi tốt nghiệp THPT là 23.50 điểm cho tổ hợp A00 (Toán, Lý, Hóa) và 24.20 điểm cho tổ hợp A01 (Toán, Lý, Anh)."

CÂU HỎI: {query_str}

ĐOẠN VĂN GIẢ ĐỊNH (2-3 câu):"""
)


class QueryTransformer:
    """
    Lớp chính xử lý các loại Query Transformation
    """
    
    def __init__(self, llm: LLM = None):
        """
        Args:
            llm: LLM instance, nếu None sẽ dùng Settings.llm
        """
        self.llm = llm or Settings.llm
        
    def rewrite_query(self, query: str) -> str:
        """
        Viết lại câu hỏi để tối ưu cho retrieval
        
        Args:
            query: Câu hỏi gốc
            
        Returns:
            Câu hỏi đã được tối ưu
        """
        with LogContext(logger, "query_rewrite", original_query=query):
            start_time = time.time()
            
            prompt = QUERY_REWRITE_PROMPT.format(query_str=query)
            response = self.llm.complete(prompt)
            rewritten = response.text.strip()
            
            duration_ms = (time.time() - start_time) * 1000
            track_rag_operation("query_transform", duration_ms, strategy="rewrite")
            
            logger.info(
                "Query rewritten",
                context={
                    "original": query,
                    "rewritten": rewritten,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            
            print(f"\n🔄 Query Rewriting:")
            print(f"   Original: {query}")
            print(f"   Rewritten: {rewritten}")
            
            return rewritten
    
    def decompose_query(self, query: str) -> List[str]:
        """
        Phân rá câu hỏi phức tạp thành các câu hỏi con
        
        Args:
            query: Câu hỏi có thể phức tạp
            
        Returns:
            List các câu hỏi con (hoặc chỉ câu hỏi gốc nếu đơn giản)
        """
        prompt = QUERY_DECOMPOSE_PROMPT.format(query_str=query)
        response = self.llm.complete(prompt)
        result = response.text.strip()
        
        if result.upper() == "SIMPLE":
            print(f"\n📝 Query Decomposition: SIMPLE (không cần phân rã)")
            return [query]
        
        # Tách các dòng thành sub-queries
        sub_queries = [q.strip() for q in result.split('\n') if q.strip()]
        
        print(f"\n🔀 Query Decomposition: {len(sub_queries)} sub-queries")
        for i, sq in enumerate(sub_queries, 1):
            print(f"   {i}. {sq}")
        
        return sub_queries
    
    def generate_multi_queries(self, query: str) -> List[str]:
        """
        Tạo nhiều biến thể của câu hỏi gốc
        
        Args:
            query: Câu hỏi gốc
            
        Returns:
            List các biến thể câu hỏi (bao gồm cả câu gốc)
        """
        prompt = MULTI_QUERY_PROMPT.format(query_str=query)
        response = self.llm.complete(prompt)
        result = response.text.strip()
        
        # Tách các dòng
        variants = [q.strip() for q in result.split('\n') if q.strip()]
        
        # Thêm câu hỏi gốc vào đầu
        all_queries = [query] + variants
        
        print(f"\n🎯 Multi-Query Generation: {len(all_queries)} variants")
        for i, q in enumerate(all_queries, 1):
            print(f"   {i}. {q}")
        
        return all_queries
    
    def generate_hyde_document(self, query: str) -> str:
        """
        Tạo tài liệu giả định để embed thay vì embed trực tiếp query
        
        Args:
            query: Câu hỏi gốc
            
        Returns:
            Đoạn văn giả định
        """
        prompt = HYDE_PROMPT.format(query_str=query)
        response = self.llm.complete(prompt)
        hyde_doc = response.text.strip()
        
        print(f"\n📄 HyDE Document Generated:")
        print(f"   {hyde_doc[:200]}...")
        
        return hyde_doc
    
    def transform_query(
        self, 
        query: str,
        strategy: str = "rewrite"
    ) -> Dict[str, Any]:
        """
        Pipeline chính - Áp dụng strategy transformation
        
        Args:
            query: Câu hỏi gốc
            strategy: Chiến lược ["rewrite", "decompose", "multi_query", "hyde", "full"]
            
        Returns:
            Dict chứa các transformed queries và metadata
        """
        result = {
            "original_query": query,
            "strategy": strategy,
            "transformed_queries": [],
            "metadata": {}
        }
        
        if strategy == "rewrite":
            rewritten = self.rewrite_query(query)
            result["transformed_queries"] = [rewritten]
            
        elif strategy == "decompose":
            sub_queries = self.decompose_query(query)
            result["transformed_queries"] = sub_queries
            result["metadata"]["is_decomposed"] = len(sub_queries) > 1
            
        elif strategy == "multi_query":
            variants = self.generate_multi_queries(query)
            result["transformed_queries"] = variants
            result["metadata"]["num_variants"] = len(variants)
            
        elif strategy == "hyde":
            hyde_doc = self.generate_hyde_document(query)
            result["transformed_queries"] = [hyde_doc]
            result["metadata"]["is_hyde"] = True
            
        elif strategy == "full":
            # Kết hợp: Rewrite -> Decompose -> Multi-query
            rewritten = self.rewrite_query(query)
            sub_queries = self.decompose_query(rewritten)
            
            all_queries = []
            for sq in sub_queries:
                variants = self.generate_multi_queries(sq)
                all_queries.extend(variants)
            
            # Remove duplicates
            result["transformed_queries"] = list(set(all_queries))
            result["metadata"]["full_pipeline"] = True
            result["metadata"]["total_queries"] = len(result["transformed_queries"])
            
        else:
            # Mặc định: không transform
            result["transformed_queries"] = [query]
        
        return result


# ==========================================
# 5. HELPER FUNCTIONS
# ==========================================

def create_query_transformer(llm: LLM = None) -> QueryTransformer:
    """
    Factory function để tạo QueryTransformer instance
    """
    return QueryTransformer(llm=llm)
