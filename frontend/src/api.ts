export class ApiError extends Error {
  constructor(public status: number, message: string, public fields: string[] = [], public code=''){super(message);}
}
/** Only the application backend is reachable from the browser. Recsys credentials stay on the server. */
export async function api<T>(path: string, token='', body?: unknown, method='POST', extraHeaders: Record<string,string>={}): Promise<T> {
  let response: Response;
  try {
    response=await fetch(`/api${path}`,{method: body===undefined?'GET':method,signal:AbortSignal.timeout(25000),
      headers:{...(token?{Authorization:`Bearer ${token}`} : {}),...(body!==undefined?{'Content-Type':'application/json'}:{}),...extraHeaders},
      ...(body!==undefined?{body:JSON.stringify(body)}:{})});
  }catch{throw new ApiError(0,'Не удалось связаться с сервисом. Проверьте подключение и попробуйте ещё раз.');}
  const result=await response.json().catch(()=>null);
  if(!response.ok)throw new ApiError(response.status,result?.detail??(response.status===401?'Войдите в кабинет, чтобы продолжить.':'Не удалось выполнить действие. Попробуйте ещё раз.'),result?.fields??[],result?.code??'');
  return result as T;
}
export async function upload(path: string, token: string, body: FormData): Promise<void>{
  const response=await fetch(`/api${path}`,{method:'POST',headers:{Authorization:`Bearer ${token}`},body,signal:AbortSignal.timeout(30000)});
  if(!response.ok){const error=await response.json().catch(()=>null);throw new ApiError(response.status,error?.detail??'Не удалось загрузить документ.');}
}
