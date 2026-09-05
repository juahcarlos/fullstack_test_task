import type { FileItem, AlertItem } from "../types/file";

const baseUrl = process.env.NEXT_PUBLIC_API_URL;



async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // ответ не JSON — используем запасной текст
  }
  return fallback;
}



export async function getFiles(): Promise<FileItem[]> {
  const response = await fetch(`${baseUrl}/files`, { cache: "no-store" });

  if (!response.ok) {
  throw new Error(await extractErrorMessage(response, "Не удалось загрузить файлы"));
  }

  return response.json();
}

export async function getAlerts(): Promise<AlertItem[]> {
  const response = await fetch(`${baseUrl}/alerts`, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Не удалось загрузить алерты"));
  }

  return response.json();
}

export async function uploadFile(title: string, file: File): Promise<FileItem> {
  const formData = new FormData();
  formData.append("title", title);
  formData.append("file", file);

  const response = await fetch(`${baseUrl}/files`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Не удалось загрузить файл"));
  }

  return response.json();
}

export async function updateFile(fileId: string, title: string): Promise<FileItem> {
  const response = await fetch(`${baseUrl}/files/${fileId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Не удалось обновить файл"));
  }

  return response.json();
}

export async function deleteFile(fileId: string): Promise<void> {
  const response = await fetch(`${baseUrl}/files/${fileId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "Не удалось удалить файл"));
  }
}

export function getDownloadUrl(fileId: string): string {
  return `${baseUrl}/files/${fileId}/download`;
}