/**
 * Strongly typed API definitions matching backend Corbel models.
 */

export interface DatabaseHealth {
  status: 'connected' | 'disconnected' | 'degraded';
  latency_ms: number | null;
  details: string | null;
}

export interface SystemHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
  database: DatabaseHealth;
}

export interface ErrorResponse {
  error: string;
  message: string;
  details?: unknown;
  correlation_id?: string | null;
}
