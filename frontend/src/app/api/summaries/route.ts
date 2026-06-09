import { NextResponse } from "next/server";

const backendUrl = process.env.BONCHMIND_API_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.text();

    const response = await fetch(`${backendUrl}/api/summaries`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    });

    const text = await response.text();

    return new Response(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json; charset=utf-8",
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown proxy error";

    return NextResponse.json(
      {
        text: `Ошибка proxy: ${message}`,
        diagnostics: "",
      },
      { status: 502 },
    );
  }
}
