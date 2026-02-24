import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import LandingPage from "./LandingPage.jsx";
import "./index.css";

const pathParts = window.location.pathname.split("/").filter(Boolean);
const firstSegment = String(pathParts[0] || "").toLowerCase();
const authEntryRoutes = new Set(["sign-in", "signin", "login", "sign-up", "signup"]);

const isLandingRoute = pathParts.length === 0 || authEntryRoutes.has(firstSegment);

let initialAuthMode = null;
if (firstSegment === "sign-up" || firstSegment === "signup") {
  initialAuthMode = "signUp";
}
if (firstSegment === "sign-in" || firstSegment === "signin" || firstSegment === "login") {
  initialAuthMode = "signIn";
}

createRoot(document.getElementById("root")).render(
  isLandingRoute ? <LandingPage initialAuthMode={initialAuthMode} /> : <App />,
);
