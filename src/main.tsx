import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AdminPanel from "./pages/Admin";
import "./index.css";

const root = document.getElementById("root");

if (!root) {
	throw new Error("Root element #root not found");
}

// Hash-based routing keeps the SPA working without server-side rewrite rules.
// Visit /#/admin for the admin panel, anything else renders the chat app.
const isAdmin = location.hash === "#/admin";

ReactDOM.createRoot(root).render(
	<React.StrictMode>
		{isAdmin ? <AdminPanel /> : <App />}
	</React.StrictMode>
);
