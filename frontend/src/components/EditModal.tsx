import { FormEvent, useEffect, useState } from "react";
import { Button, Form, Modal } from "react-bootstrap";
import type { FileItem } from "../types/file";

type Props = {
  file: FileItem | null;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (fileId: string, title: string) => Promise<void>;
};

export function EditModal({ file, isSubmitting, onClose, onSubmit }: Props) {
  const [title, setTitle] = useState("");

  useEffect(() => {
    if (file) {
      setTitle(file.title);
    }
  }, [file]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!file || !title.trim()) {
      return;
    }

    await onSubmit(file.id, title.trim());
  }

  return (
    <Modal show={file !== null} onHide={onClose} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Изменить название</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group>
            <Form.Label>Название</Form.Label>
            <Form.Control value={title} onChange={(event) => setTitle(event.target.value)} />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}