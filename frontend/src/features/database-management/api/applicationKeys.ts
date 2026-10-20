import { apiDelete, apiGet, apiPost, apiPut } from '../../../api';

export interface ApplicationKeyChoice { id: number; name: string; username: string; }
export interface ApplicationKey extends ApplicationKeyChoice { hasPassword: boolean; connectionCount: number; remark: string; }
export interface ApplicationKeyPayload { name: string; username: string; password: string; remark: string; }
const base = '/api/application-keys/';
export const listApplicationKeys = () => apiGet<ApplicationKey[]>(base);
export const selectApplicationKeys = () => apiGet<ApplicationKeyChoice[]>(`${base}?select=1`);
export const createApplicationKey = (value: ApplicationKeyPayload) => apiPost<ApplicationKey>(base, value);
export const updateApplicationKey = (id: number, value: ApplicationKeyPayload) => apiPut<ApplicationKey>(`${base}${id}/`, value);
export const deleteApplicationKey = (id: number) => apiDelete(`${base}${id}/`);
