self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_error) {
    payload = {};
  }
  const title = payload.title || "C3PO";
  event.waitUntil(self.registration.showNotification(title, {
    body: payload.body || "Novo alerta operacional",
    icon: "/c3po-icon-192-v2.png",
    badge: "/c3po-icon-192-v2.png",
    data: {
      deepLink: payload.deep_link || "/",
      category: payload.category || "unknown"
    }
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.deepLink || "/", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const existing = windows.find((client) => new URL(client.url).origin === self.location.origin);
    if (existing) {
      await existing.navigate(target);
      return existing.focus();
    }
    return self.clients.openWindow(target);
  })());
});
