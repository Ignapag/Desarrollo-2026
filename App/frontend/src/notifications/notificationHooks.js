// Contexto y hooks del centro de notificaciones: acceso a los avisos y a la recarga de la bandeja.
import { createContext, useContext } from 'react';
export const NotificationContext = createContext(null);
export const useNotifications = () => useContext(NotificationContext);
export const useNotificationInboxLoader = () => useContext(NotificationContext)?.refreshInbox;
