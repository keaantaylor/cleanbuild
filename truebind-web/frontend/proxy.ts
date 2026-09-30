import { NextResponse, userAgent, type NextRequest } from "next/server";

/** Device class from the request's user agent. iPadOS reports itself as a Mac,
 * so the browser corrects "desktop" to "tablet" before paint (see DEVICE_SCRIPT). */
type DeviceClass = "phone" | "tablet" | "desktop";

function deviceClass(ua: ReturnType<typeof userAgent>): DeviceClass {
  if (ua.device.type === "mobile" || ua.device.type === "wearable") return "phone";
  if (ua.device.type === "tablet") return "tablet";
  return "desktop";
}

// Tells the page which kind of device asked for it, so the first paint already
// uses the phone or tablet layout. Pages stay static: the class travels in a
// cookie and a response header, not in the rendered HTML.
export function proxy(request: NextRequest) {
  const device = deviceClass(userAgent(request));
  const res = NextResponse.next();
  res.headers.set("x-truebind-device", device);
  if (request.cookies.get("tb-device")?.value !== device) {
    res.cookies.set("tb-device", device, { path: "/", sameSite: "lax", secure: request.nextUrl.protocol === "https:", maxAge: 60 * 60 * 24 * 30 });
  }
  return res;
}

export const config = {
  // Pages only: never the API proxy, build assets or public files.
  matcher: ["/((?!api/|_next/|assets/|fonts/|favicon.ico).*)"],
};
