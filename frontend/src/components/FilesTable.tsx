import { Badge, Button, Table } from "react-bootstrap";
import type { FileItem } from "../types/file";
import { formatDate, formatSize, getProcessingVariant } from "../lib/format";
import { getDownloadUrl } from "../lib/api";

type Props = {
  files: FileItem[];
  onEdit: (file: FileItem) => void;
  onDelete: (fileId: string) => void;
};

export function FilesTable({ files, onEdit, onDelete }: Props) {
  if (files.length === 0) {
    return <p className="text-center py-4 text-secondary mb-0">Файлы пока не загружены</p>;
  }

  return (
    <div className="table-responsive">
      <Table hover bordered className="align-middle mb-0">
        <thead className="table-light">
          <tr>
            <th>Название</th>
            <th>Файл</th>
            <th>MIME</th>
            <th>Размер</th>
            <th>Статус</th>
            <th>Проверка</th>
            <th>Создан</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={file.id}>
              <td>
                <div className="fw-semibold">{file.title}</div>
                <div className="small text-secondary">{file.id}</div>
              </td>
              <td>{file.original_name}</td>
              <td>{file.mime_type}</td>
              <td>{formatSize(file.size)}</td>
              <td>
                <Badge bg={getProcessingVariant(file.processing_status)}>
                  {file.processing_status}
                </Badge>
              </td>
              <td>
                <div className="d-flex flex-column gap-1">
                  <Badge bg={file.requires_attention ? "warning" : "success"}>
                    {file.scan_status ?? "pending"}
                  </Badge>
                  <span className="small text-secondary">
                    {file.scan_details ?? "Ожидает обработки"}
                  </span>
                </div>
              </td>
              <td>{formatDate(file.created_at)}</td>
              <td className="text-nowrap">
                <div className="d-flex gap-2">
                  <Button as="a" href={getDownloadUrl(file.id)} variant="outline-primary" size="sm">
                    Скачать
                  </Button>
                  <Button variant="outline-secondary" size="sm" onClick={() => onEdit(file)}>
                    Изменить
                  </Button>
                  <Button variant="outline-danger" size="sm" onClick={() => onDelete(file.id)}>
                    Удалить
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}