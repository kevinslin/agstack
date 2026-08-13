import {
  dashboardResponse,
  dashboardSessionId,
  requireDashboardIdentity,
} from "@/app/api/_lib/dashboard";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ session: string }> },
): Promise<Response> {
  const denied = requireDashboardIdentity(request);
  if (denied) return denied;

  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return dashboardResponse({ error: "invalid origin" }, 403);
  }

  const { session } = await params;

  if (!dashboardSessionId(session)) {
    return dashboardResponse({ error: "task not found" }, 404);
  }

  return dashboardResponse(
    { error: "Hosted file attachments require configured object storage." },
    501,
  );
}
