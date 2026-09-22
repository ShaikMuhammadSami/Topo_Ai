export const dynamic = "force-static"

export function GET(): Response {
  return Response.json({
    status: "ok",
    component: "frontend",
  })
}
