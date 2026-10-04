import { App } from "@/components/app";
import { connection } from "next/server";
export default async function Page() { await connection(); return <App />; }
