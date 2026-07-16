from __future__ import annotations


from rpp_plugin_types.rpp_common import MotionController2D
from rpp_plugin_types.rpp_common import DisturbanceGenerator2D


COMPONENTS = {
    "ctl_main": "rpp_common::MotionController2D",
    "ctl_disturbance": "rpp_common::DisturbanceGenerator2D",
}

class ComponentPluginPy(MotionController2D):
    def __init__(self):
        super().__init__()

    def validate(self, state : MotionController2D.Pose2D) -> bool:

        x = state.position.x
        return x > 5.0

    def step(self, state: MotionController2D.Pose2D, dt: float) -> None:
        # Implement the control logic here
        pass
