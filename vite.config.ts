import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
	plugins: [react()],
	server: {
		proxy: {
			"/chat": "http://localhost:3000",
			"/stop": "http://localhost:3000",
			"/history": "http://localhost:3000",
			"/rag-stats": "http://localhost:3000",
			"/admin-login": "http://localhost:3000",
			"/admin-files": "http://localhost:3000",
			"/admin-upload": "http://localhost:3000",
			"/admin-delete": "http://localhost:3000",
			"/admin-rebuild": "http://localhost:3000",
		},
	},
});
