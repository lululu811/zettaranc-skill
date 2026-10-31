"""模拟器路由"""

from api.utils.errors import raise_api_error
from fastapi import APIRouter, HTTPException

from api.models.simulator import SimulationRequest, SimulationResponse
from api.services import simulator_service

router = APIRouter()


@router.post("/run", response_model=SimulationResponse)
def run_simulation(req: SimulationRequest):
    try:
        return simulator_service.run_simulation_service(req)
    except Exception as e:
        raise_api_error(e, prefix="模拟失败")


@router.post("/walk-forward", response_model=dict)
def run_walk_forward(req: SimulationRequest):
    try:
        return simulator_service.run_walk_forward_service(req)
    except Exception as e:
        raise_api_error(e, prefix="Walk-forward 寻优失败")
