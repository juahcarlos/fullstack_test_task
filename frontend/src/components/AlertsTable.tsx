import { Badge, Table } from "react-bootstrap";
import type { AlertItem } from "../types/file";
import { formatDate, getLevelVariant } from "../lib/format";

type Props = {
  alerts: AlertItem[];
};

export function AlertsTable({ alerts }: Props) {
  if (alerts.length === 0) {
    return <p className="text-center py-4 text-secondary mb-0">Алертов пока нет</p>;
  }

  return (
    <div className="table-responsive">
      <Table hover bordered className="align-middle mb-0">
        <thead className="table-light">
          <tr>
            <th>ID</th>
            <th>File ID</th>
            <th>Уровень</th>
            <th>Сообщение</th>
            <th>Создан</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((item) => (
            <tr key={item.id}>
              <td>{item.id}</td>
              <td className="small">{item.file_id}</td>
              <td>
                <Badge bg={getLevelVariant(item.level)}>{item.level}</Badge>
              </td>
              <td>{item.message}</td>
              <td>{formatDate(item.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}