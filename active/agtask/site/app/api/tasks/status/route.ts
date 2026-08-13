import { handleDashboardStatusUpdate } from "@/app/api/_lib/dashboard";

export async function PATCH(request: Request): Promise<Response> {
  return handleDashboardStatusUpdate(request, null);
}
