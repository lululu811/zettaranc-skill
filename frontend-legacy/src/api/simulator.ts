import api from './client';
import type { SimulationRequest, SimulationResponse } from './types';

export async function runSimulation(params: SimulationRequest): Promise<SimulationResponse> {
  const { data } = await api.post<SimulationResponse>('/simulator/run', params);
  return data;
}

export async function runWalkForward(params: SimulationRequest): Promise<Record<string, unknown>> {
  const { data } = await api.post('/simulator/walk-forward', params);
  return data;
}
