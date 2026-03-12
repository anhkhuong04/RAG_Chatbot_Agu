import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { LandingPage, ChatPage, AdminPage } from "./pages";

/**
 * App Component - Router Setup
 * "/" - Landing Page (Homepage)
 * "/chat" - Chat Application
 * "/admin" - Admin Dashboard
 */
function App() {
  return (
    <Router>
      <Routes>
        {/* Landing Page - Homepage */}
        <Route path="/" element={<LandingPage />} />

        {/* Chat Page - Chatbot Interface */}
        <Route path="/chat" element={<ChatPage />} />

        {/* Admin Page - Knowledge Base Management */}
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </Router>
  );
}

export default App;
