import {
  dashboardResponse,
  dashboardSessionId,
  handleDashboardStatusUpdate,
  requireDashboardIdentity,
} from "@/app/api/_lib/dashboard";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ session: string }> },
): Promise<Response> {
  const denied = requireDashboardIdentity(request);
  if (denied) return denied;

  const { session } = await params;
  const sessionId = dashboardSessionId(session);

  if (!sessionId) {
    return dashboardResponse({ error: "task not found" }, 404);
  }

  return handleDashboardStatusUpdate(request, sessionId);
}
