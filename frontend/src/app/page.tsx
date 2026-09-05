"use client";

import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Button, Card, Col, Container, Row, Spinner } from "react-bootstrap";
import type { FileItem, AlertItem } from "../types/file";
import { getFiles, getAlerts, uploadFile, updateFile, deleteFile } from "../lib/api";
import { FilesTable } from "../components/FilesTable";
import { AlertsTable } from "../components/AlertsTable";
import { UploadModal } from "../components/UploadModal";
import { EditModal } from "../components/EditModal";

export default function Page() {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [editingFile, setEditingFile] = useState<FileItem | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const requestIdRef = useRef(0);

  async function loadData() {
    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [filesData, alertsData] = await Promise.all([getFiles(), getAlerts()]);

      if (requestId !== requestIdRef.current) {
        return;
      }

      setFiles(filesData);
      setAlerts(alertsData);
    } catch (error) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleUpload(title: string, file: File) {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await uploadFile(title, file);
      setShowUploadModal(false);
      await loadData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleEdit(fileId: string, title: string) {
    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      await updateFile(fileId, title);
      setEditingFile(null);
      await loadData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(fileId: string) {
    setErrorMessage(null);

    try {
      await deleteFile(fileId);
      await loadData();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Произошла ошибка");
    }
  }

  return (
    <Container fluid className="py-4 px-4 bg-light min-vh-100">
      <Row className="justify-content-center">
        <Col xxl={10} xl={11}>
          <Card className="shadow-sm border-0 mb-4">
            <Card.Body className="p-4">
              <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
                <div>
                  <h1 className="h3 mb-2">Управление файлами</h1>
                  <p className="text-secondary mb-0">
                    Загрузка файлов, просмотр статусов обработки и ленты алертов.
                  </p>
                </div>
                <div className="d-flex gap-2">
                  <Button variant="outline-secondary" onClick={() => void loadData()}>
                    Обновить
                  </Button>
                  <Button variant="primary" onClick={() => setShowUploadModal(true)}>
                    Добавить файл
                  </Button>
                </div>
              </div>
            </Card.Body>
          </Card>

          {errorMessage ? (
            <Alert variant="danger" className="shadow-sm">
              {errorMessage}
            </Alert>
          ) : null}

          <Card className="shadow-sm border-0 mb-4">
            <Card.Header className="bg-white border-0 pt-4 px-4">
              <div className="d-flex justify-content-between align-items-center">
                <h2 className="h5 mb-0">Файлы</h2>
                <Badge bg="secondary">{files.length}</Badge>
              </div>
            </Card.Header>
            <Card.Body className="px-4 pb-4">
              {isLoading ? (
                <div className="d-flex justify-content-center py-5">
                  <Spinner animation="border" />
                </div>
              ) : (
                <FilesTable files={files} onEdit={setEditingFile} onDelete={(id) => void handleDelete(id)} />
              )}
            </Card.Body>
          </Card>

          <Card className="shadow-sm border-0">
            <Card.Header className="bg-white border-0 pt-4 px-4">
              <div className="d-flex justify-content-between align-items-center">
                <h2 className="h5 mb-0">Алерты</h2>
                <Badge bg="secondary">{alerts.length}</Badge>
              </div>
            </Card.Header>
            <Card.Body className="px-4 pb-4">
              {isLoading ? (
                <div className="d-flex justify-content-center py-5">
                  <Spinner animation="border" />
                </div>
              ) : (
                <AlertsTable alerts={alerts} />
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <UploadModal
        show={showUploadModal}
        isSubmitting={isSubmitting}
        onClose={() => setShowUploadModal(false)}
        onSubmit={handleUpload}
      />

      <EditModal
        file={editingFile}
        isSubmitting={isSubmitting}
        onClose={() => setEditingFile(null)}
        onSubmit={handleEdit}
      />
    </Container>
  );
}