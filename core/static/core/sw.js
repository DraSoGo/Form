self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',()=>{});
self.addEventListener('push',event=>{let data={};try{data=event.data.json()}catch{}event.waitUntil(self.registration.showNotification('Form · Fitness',{body:'Your fitness update is ready.',icon:'/static/core/icon-192.png',badge:'/static/core/icon-192.png',data:{url:'/coach/'}}))});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(self.clients.openWindow('/coach/'))});
