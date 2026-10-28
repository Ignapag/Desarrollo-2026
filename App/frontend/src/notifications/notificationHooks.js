import { createContext, useContext } from 'react';
export const NotificationContext = createContext(null);
export const useNotifications = () => useContext(NotificationContext);
export const useNotificationInboxLoader = () => useContext(NotificationContext)?.refreshInbox;
