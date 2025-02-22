from python_qt_binding import loadUi
from python_qt_binding.QtWidgets import QWidget
from python_qt_binding.QtCore import QTimer

import rospy
import resource_retriever as rr
from tf.transformations import euler_from_quaternion, quaternion_from_euler
import dynamic_reconfigure.client
import numpy as np
import rosservice

from std_srvs.srv import SetBool
from geometry_msgs.msg import Pose, Twist, Point, Quaternion, Vector3

from gui.pose_twist_dialog import PoseTwistDialog
from gui.pid_dialog import PidDialog
import math


class ControlsWidget(QWidget):

    DIRS = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']
    PID = ['p', 'i', 'd']
    DESIRED_POSE_TOPIC = 'controls/desired_pose'
    DESIRED_TWIST_TOPIC = 'controls/desired_twist'
    DESIRED_POWER_TOPIC = 'controls/desired_power'
    ENABLE_SERVICE = 'enable_controls'

    def __init__(self):

        super(ControlsWidget, self).__init__()

        ui_file = rr.get_filename('package://gui/resource/ControlsWidget.ui', use_protocol=False)
        loadUi(ui_file, self)

        self.setObjectName('ControlsWidget')

        self.background_colors = {
            "green": "background-color: #8aff92",
            "red": "background-color: #ff7878"
        }
        self.controls_button_text = {
            "enable": "Enable Controls",
            "disable": "Disable Controls"
        }
        self.enable_controls_button.clicked.connect(self.enable_state_clicked)
        self.enable_controls_button.setText(self.controls_button_text["enable"])
        self.enable_controls_button.setStyleSheet(self.background_colors["green"])

        self.enable_controls_timer = QTimer(self)
        self.enable_controls_timer.timeout.connect(self.check_enable_controls)
        self.enable_controls_timer.start(100)

        self.state_times = {
            'pose': rospy.Time.now(),
            'twist': rospy.Time.now(),
            'power': rospy.Time.now()
        }

        self.desired_pose_sub = rospy.Subscriber(self.DESIRED_POSE_TOPIC, Pose, self.pose_received)
        self.desired_twist_sub = rospy.Subscriber(self.DESIRED_TWIST_TOPIC, Twist, self.twist_received)
        self.desired_power_sub = rospy.Subscriber(self.DESIRED_POWER_TOPIC, Twist, self.power_received)

        self.gui_publishing = False
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.check_times)
        self.state_timer.setInterval(100)
        self.state_timer.start()
        self.publishing_timer = QTimer(self)
        self.publishing_timer.timeout.connect(self.publish_controls)
        self.publishing_timer.setInterval(60)

        self.pose_twist_dialog = PoseTwistDialog()
        self.pose_twist_dialog.pose.connect(self.pose_entered)
        self.pose_twist_dialog.twist.connect(self.twist_entered)

        self.update_controls_button.setText('Set Desired Pose/Twist')
        self.update_controls_button.clicked.connect(self.update_controls_clicked)

        self.pos_pid = [
            [self.x_pos_p, self.x_pos_i, self.x_pos_d],
            [self.y_pos_p, self.y_pos_i, self.y_pos_d],
            [self.z_pos_p, self.z_pos_i, self.z_pos_d],
            [self.roll_pos_p, self.roll_pos_i, self.roll_pos_d],
            [self.pitch_pos_p, self.pitch_pos_i, self.pitch_pos_d],
            [self.yaw_pos_p, self.yaw_pos_i, self.yaw_pos_d]
        ]

        self.vel_pid = [
            [self.x_vel_p, self.x_vel_i, self.x_vel_d],
            [self.y_vel_p, self.y_vel_i, self.y_vel_d],
            [self.z_vel_p, self.z_vel_i, self.z_vel_d],
            [self.roll_vel_p, self.roll_vel_i, self.roll_vel_d],
            [self.pitch_vel_p, self.pitch_vel_i, self.pitch_vel_d],
            [self.yaw_vel_p, self.yaw_vel_i, self.yaw_vel_d]
        ]

        self.pos_pid_timer = QTimer(self)
        self.pos_pid_timer.timeout.connect(lambda pid_list=self.pos_pid: self.update_pid_display(pid_list, 'pos'))
        self.pos_pid_timer.start(200)

        self.vel_pid_timer = QTimer(self)
        self.vel_pid_timer.timeout.connect(lambda pid_list=self.vel_pid: self.update_pid_display(pid_list, 'vel'))
        self.vel_pid_timer.start(200)

        self.pid_dialog = PidDialog()
        self.pid_dialog.pid.connect(self.update_pid_constants)

        self.pid_service_timer = QTimer(self)
        self.pid_service_timer.timeout.connect(self.check_pid_service)
        self.pid_service_timer.start(100)

        self.update_pid_button.clicked.connect(self.show_pid_dialog)

        self.tab_widget.setTabText(0, 'Position')
        self.tab_widget.setTabText(1, 'Velocity')
        self.tab_widget.setCurrentIndex(0)

        rospy.loginfo("Controls Widget successfully initialized")

    def enable_state_clicked(self):
        rospy.wait_for_service(self.ENABLE_SERVICE)
        enable_state = self.enable_controls_button.text() == self.controls_button_text['enable']

        if enable_state:
            self.enable_controls_button.setStyleSheet(self.background_colors["red"])
            self.enable_controls_button.setText(self.controls_button_text["disable"])
        else:
            self.enable_controls_button.setStyleSheet(self.background_colors["green"])
            self.enable_controls_button.setText(self.controls_button_text["enable"])

        try:
            enable_controls = rospy.ServiceProxy(self.ENABLE_SERVICE, SetBool)
            _ = enable_controls(enable_state)
        except rospy.ServiceException as e:
            print(f"Service call failed: {e}")

    def check_enable_controls(self):
        self.enable_controls_button.setEnabled(f'/{self.ENABLE_SERVICE}' in rosservice.get_service_list())

    def pose_received(self, pose):
        self.state_times['pose'] = rospy.Time.now()
        self.controls_type_label.setText('Pose')
        roll, pitch, yaw = euler_from_quaternion((pose.orientation.x, pose.orientation.y,
                                                  pose.orientation.z, pose.orientation.w))
        self.update_desired_state((pose.position.x, pose.position.y, pose.position.z,
                                   roll, pitch, yaw))

    def twist_received(self, twist):
        self.state_times['twist'] = rospy.Time.now()
        self.controls_type_label.setText('Twist')
        self.update_desired_state((twist.linear.x, twist.linear.y, twist.linear.z,
                                  twist.angular.x, twist.angular.y, twist.angular.z))

    def power_received(self, power):
        self.state_times['power'] = rospy.Time.now()
        self.controls_type_label.setText('Power')
        self.update_desired_state((power.linear.x, power.linear.y, power.linear.z,
                                  power.angular.x, power.angular.y, power.angular.z))

    def update_desired_state(self, vals):
        self.desired_control_box.setEnabled(True)
        self.x_value.setValue(vals[0])
        self.y_value.setValue(vals[1])
        self.z_value.setValue(vals[2])
        self.roll_value.setValue(np.degrees(vals[3]))
        self.pitch_value.setValue(np.degrees(vals[4]))
        self.yaw_value.setValue(np.degrees(vals[5]))

    def publish_controls(self):
        self.pub.publish(self.controls_msg)

    def check_times(self):
        for key in self.state_times:
            if rospy.Time.now() - self.state_times[key] < rospy.Duration(3):
                self.update_controls_button.setEnabled(False)
                return
        self.controls_type_label.setText('None')
        self.desired_control_box.setEnabled(False)
        self.update_controls_button.setEnabled(True)

    def update_controls_clicked(self):
        if self.gui_publishing:
            self.update_controls_button.setText('Set Desired Pose/Twist')
            self.publishing_timer.stop()
            self.state_timer.start()
            self.gui_publishing = False
        else:
            self.pose_twist_dialog.show()

    def pose_twist_entered(self):
        self.state_timer.stop()
        self.update_controls_button.setText('Stop Publishing')
        self.update_controls_button.setEnabled(True)
        self.gui_publishing = True
        self.publishing_timer.start()

    def pose_entered(self, x, y, z, roll, pitch, yaw):
        self.pub = rospy.Publisher(self.DESIRED_POSE_TOPIC, Pose, queue_size=3)
        quat = quaternion_from_euler(np.radians(roll), np.radians(pitch), np.radians(yaw))
        self.controls_msg = Pose(position=Point(x=x, y=y, z=z), orientation=Quaternion(*quat))
        self.pose_twist_entered()

    def twist_entered(self, x, y, z, roll, pitch, yaw):
        self.pub = rospy.Publisher(self.DESIRED_TWIST_TOPIC, Twist, queue_size=3)
        self.controls_msg = Twist(linear=Vector3(x=x, y=y, z=z), angular=Vector3(x=roll, y=pitch, z=yaw))
        self.pose_twist_entered()

    def get_pid_param(self, pid_type, i, k):
        param_name = f'controls/{self.DIRS[i]}_{pid_type}/controller/K{self.PID[k]}'
        if not rospy.has_param(param_name) or not rospy.has_param(param_name + '_scale'):
            return None
        return rospy.get_param(param_name) * rospy.get_param(param_name + '_scale')

    def update_pid_display(self, pid_list, pid_type):
        for i in range(len(self.DIRS)):
            for k in range(len(self.PID)):
                param_value = self.get_pid_param(pid_type, i, k)
                if param_value is not None:
                    pid_list[i][k].setEnabled(True)
                    pid_list[i][k].setValue(param_value)
                else:
                    pid_list[i][k].setEnabled(False)

    def show_pid_dialog(self):
        ppid = [[0 for i in range(len(self.PID))] for k in range(len(self.DIRS))]
        vpid = [[0 for i in range(len(self.PID))] for k in range(len(self.DIRS))]
        for i in range(len(self.DIRS)):
            for k in range(len(self.PID)):
                pos_param = self.get_pid_param('pos', i, k)
                ppid[i][k] = pos_param if pos_param is not None else 0
                vel_param = self.get_pid_param('vel', i, k)
                vpid[i][k] = vel_param if vel_param is not None else 0
        self.pid_dialog.show(ppid, vpid)

    def check_pid_service(self):
        service_list = rosservice.get_service_list()
        for i in range(len(self.DIRS)):
            if f'/controls/{self.DIRS[i]}_pos/controller/set_parameters' not in service_list:
                self.pid_box.setEnabled(False)
                self.update_pid_button.setEnabled(False)
                return
        self.pid_box.setEnabled(True)
        self.update_pid_button.setEnabled(True)

    def update_pid_constants(self, ppid, vpid):
        for i in range(len(self.DIRS)):
            pos_client = dynamic_reconfigure.client.Client(f'/controls/{self.DIRS[i]}_pos/controller')
            ppid_scal = [1.0, 1.0, 1.0]
            vpid_scal = [1.0, 1.0, 1.0]
            for k in range(3):
                if ppid[i][k] > 1:
                    ppid_scal[k] = 10**(math.floor(math.log10(ppid[i][k])) + 1)
                    ppid[i][k] = ppid[i][k]/ppid_scal[k]
                if vpid[i][k] > 1:
                    vpid_scal[k] = 10**(math.floor(math.log10(vpid[i][k])) + 1)
                    vpid[i][k] = vpid[i][k]/vpid_scal[k]

            pos_client.update_configuration({'Kp': ppid[i][0],
                                             'Ki': ppid[i][1],
                                             'Kd': ppid[i][2],
                                             'Kp_scale': ppid_scal[0],
                                             'Ki_scale': ppid_scal[1],
                                             'Kd_scale': ppid_scal[2]})
            vel_client = dynamic_reconfigure.client.Client(f'/controls/{self.DIRS[i]}_vel/controller')
            vel_client.update_configuration({'Kp': vpid[i][0],
                                             'Ki': vpid[i][1],
                                             'Kd': vpid[i][2],
                                             'Kp_scale': vpid_scal[0],
                                             'Ki_scale': vpid_scal[1],
                                             'Kd_scale': vpid_scal[2]})
