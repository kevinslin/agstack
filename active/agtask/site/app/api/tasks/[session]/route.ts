import { dashboardTaskDetail } from "@/db/dashboard";
import {
  dashboardError,
  dashboardResponse,
  dashboardSessionId,
  requireDashboardIdentity,
} from "@/app/api/_lib/dashboard";

export async function GET(
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

  if (new URL(request.url).search) {
    return dashboardResponse({ error: "task query is not supported" }, 400);
  }

  try {
    return dashboardResponse(await dashboardTaskDetail(sessionId));
  } catch (error) {
    return dashboardError(error);
  }
}
