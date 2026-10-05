// Inline scripts run before first paint. Kept out of client modules: a
// "use client" export imported by a server component is a reference, not a string.

/** Runs before first paint: tags <html data-device> with the class the server
 * detected (proxy.ts, cookie "tb-device"), correcting iPads that report as Macs. */
export const DEVICE_SCRIPT = `try{var h=document.documentElement,m=document.cookie.match(/(?:^|; )tb-device=(phone|tablet|desktop)/),d=m?m[1]:'';var touch=navigator.maxTouchPoints>1,w=Math.min(screen.width,screen.height);if(!d||(d==='desktop'&&touch&&/Macintosh/.test(navigator.userAgent)))d=touch?(w<600?'phone':'tablet'):'desktop';h.dataset.device=d;}catch(e){}`;
