import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "probelens_session";

// Optimistic check only: the API validates the session on every request.
export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  if (pathname === "/login") {
    // `next` means the app bounced here after a 401: the cookie exists but is no longer
    // valid, so let the user log in again instead of looping back to the app.
    const bounced = request.nextUrl.searchParams.has("next");
    return hasSession && !bounced ? NextResponse.redirect(new URL("/", request.url)) : NextResponse.next();
  }
  if (!hasSession) {
    const login = new URL("/login", request.url);
    if (pathname !== "/") login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
