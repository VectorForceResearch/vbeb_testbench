from visual_behavior import stage, nidaqio, source_project_configuration, init_log

config = source_project_configuration('visual_behavior_v1.yml')
stage_ = stage.PhidgetStage(x_channel=config.phidget.channels.x,
                            y_channel=config.phidget.channels.y,
                            z_channel=config.phidget.channels.z)

stage_.initialize_axis(config.phidget.channels.x)
stage_.initialize_axis(config.phidget.channels.y)
stage_.initialize_axis(config.phidget.channels.z)
stage_.serial = stage_._axes[0].getDeviceSerialNumber()

position = stage_.position
print(position)
position[1] += 5.0
stage_.move_to(position)

stage_._axes[1].setEngaged(True)
print(stage_.is_engaged)
stage_.stop_motion()
print(stage_.is_engaged)
