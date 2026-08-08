export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Product = {
  id: number; name: string; category: string; merchant: string; url: string;
  current_price_cents: number; typical_price_cents: number; currency: string; rating: number;
};

export type Decision = {
  id: number; product: Product; verdict: "BUY" | "WAIT" | "PASS"; score: number;
  budget_cents: number; evidence: string[]; explanation: string;
  prevented_spend_cents: number; created_at: string; alternatives: Product[];
};

export type Dashboard = {
  choice_score: number | null; savings_cents: number; prevented_spend_cents: number;
  points_balance: number; decision_count: number; purchase_count: number;
  verdicts: Record<"BUY" | "WAIT" | "PASS", number>;
};

export async function request<T>(path: string, token?: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail ?? "Request failed");
  }
  return response.json();
}

export function money(cents: number, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);
}

