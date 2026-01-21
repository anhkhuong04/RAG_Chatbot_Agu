import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { LandingPage, ChatPage } from "./pages";

/**
 * App Component - Router Setup
 * "/" - Landing Page (Homepage)
 * "/chat" - Chat Application
 */
function App() {
  return (
    <Router>
      <Routes>
        {/* Landing Page - Homepage */}
        <Route path="/" element={<LandingPage />} />

        {/* Chat Page - Chatbot Interface */}
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
    </Router>
  );
}

export default App;
