#!/usr/bin/env python3

import rospy
from sensor_msgs.msg import FluidPressure
from std_msgs.msg import Float64


class PressureToDepthConverter:

    NODE_NAME = "depth_pub"
    PRESSURE_SUB_TOPIC = "offboard/pressure"
    DEPTH_DEST_TOPIC = "sensors/depth"

    DENSITY_WATER = 1000
    ACCEL_GRAVITY = 9.80665
    ATMOSPHERIC_PRESSURE = 101325

    def __init__(self):
        rospy.init_node(self.NODE_NAME)
        self._pub_depth = rospy.Publisher(self.DEPTH_DEST_TOPIC, Float64, queue_size=50)
        self._sub_pressure = rospy.Subscriber(self.PRESSURE_SUB_TOPIC, FluidPressure, self.receive_pressure)
        rospy.spin()

    def receive_pressure(self, pressure):
        depth = Float64()
        depth.data = self.pressure_to_depth(pressure.fluid_pressure)
        self._pub_depth.publish(depth)

    def pressure_to_depth(self, pressure):
        return -(pressure - self.ATMOSPHERIC_PRESSURE) / (self.DENSITY_WATER * self.ACCEL_GRAVITY)


if __name__ == '__main__':
    try:
        PressureToDepthConverter()
    except rospy.ROSInterruptException:
        pass
