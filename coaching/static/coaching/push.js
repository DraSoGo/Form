(() => {
  const enable = document.getElementById('push-enable');
  if (!enable) return;
  const status = document.getElementById('push-status');
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const save = async (subscription, revoke=false) => {
    const response = await fetch('/coach/push/', {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({...subscription.toJSON(),revoke})});
    if (!response.ok) throw new Error('Could not save notification settings.');
  };
  enable.addEventListener('click', async () => {
    try {
      if (!('PushManager' in window)) throw new Error('Push is unavailable in this browser. On iOS, install the app first.');
      if (await Notification.requestPermission() !== 'granted') throw new Error('Notification permission was not granted.');
      const registration = await navigator.serviceWorker.ready;
      const encoded = enable.dataset.key.replace(/-/g,'+').replace(/_/g,'/');
      const key = Uint8Array.from(atob(encoded+'='.repeat((4-encoded.length%4)%4)),c=>c.charCodeAt(0));
      const subscription = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
      await save(subscription); status.textContent='Notifications enabled.';
    } catch (error) { status.textContent=error.message; }
  });
  document.getElementById('push-disable').addEventListener('click', async () => {
    try {
      const registration=await navigator.serviceWorker.ready;
      const subscription=await registration.pushManager.getSubscription();
      if (subscription) { await save(subscription,true); await subscription.unsubscribe(); }
      status.textContent='Notifications disabled.';
    } catch(error) { status.textContent=error.message; }
  });
})();
