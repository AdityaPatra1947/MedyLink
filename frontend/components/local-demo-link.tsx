"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, UsersRound } from "lucide-react";

/** A local development signpost; never sends credentials between environments. */
export function LocalDemoLink() {
  const [demoUrl, setDemoUrl] = useState("");
  useEffect(() => {
    const { hostname, port } = window.location;
    if (process.env.NODE_ENV === "development" && ["localhost", "127.0.0.1"].includes(hostname) && port === "3000") {
      setDemoUrl(`http://${hostname}:3001/login`);
    }
  }, []);
  if (!demoUrl) return null;
  return <div className="notice info" style={{ marginBottom: 18 }}>
    <UsersRound size={17}/>
    <span>Using the test patient or doctor accounts? Their records are in the demo workspace. <a href={demoUrl} style={{ fontWeight: 600, textDecoration: "underline", textUnderlineOffset: 3 }}>Open demo sign in <ArrowUpRight size={12} style={{ display: "inline" }}/></a></span>
  </div>;
}
