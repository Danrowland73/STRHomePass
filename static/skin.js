// The guest page's look, resolved against the device before the page paints.
// Loaded as a blocking script in the guest page's <head> and called from the
// inline script there, so a phone never flashes the standard look first.
//
// A link's page_style is "standard", "device", "ios" or "android". "device"
// becomes "ios" on iPhone, iPad and iPod and "android" on Android, and
// "standard" anywhere else. Only looks change, so a wrong guess costs a
// guest nothing but familiarity.

// iPadOS 13+ asks for desktop sites and reports itself as a Mac. A Mac with
// a touch screen does not exist, so touch points tell the two apart.
function detectGuestOS(ua, maxTouchPoints) {
  ua = ua || '';
  if (/iPhone|iPad|iPod/.test(ua)) return 'ios';
  if (/Macintosh/.test(ua) && (maxTouchPoints || 0) > 1) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  return 'other';
}

function resolvePageSkin(pageStyle, os) {
  if (pageStyle === 'ios' || pageStyle === 'android') return pageStyle;
  if (pageStyle === 'device' && (os === 'ios' || os === 'android')) return os;
  return 'standard';
}

function applyPageSkin(pageStyle) {
  var os = detectGuestOS(navigator.userAgent, navigator.maxTouchPoints);
  var skin = resolvePageSkin(pageStyle, os);
  var root = document.documentElement;
  root.setAttribute('data-os', os);
  if (skin !== 'standard') root.setAttribute('data-skin', skin);
  return skin;
}
