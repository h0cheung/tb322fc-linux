import { definePlugin } from "@decky/api";
import { Content } from "./Content";

export default definePlugin(() => {
  return {
    name: "Y700 Charge",
    content: <Content />,
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <rect x="2" y="7" width="16" height="10" rx="2" />
        <path d="M22 11v2" />
        <path d="M6 12h6" />
        <path d="M9 9v6" />
      </svg>
    ),
  };
});
