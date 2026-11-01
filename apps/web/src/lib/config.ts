export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === "true";
