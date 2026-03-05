from neurosdk.scanner import Scanner
from em_st_artifacts.utils import lib_settings
from em_st_artifacts.utils import support_classes
from em_st_artifacts import emotional_math
from neurosdk.cmn_types import *

from time import sleep


def sensor_found(scanner, sensors):
    for index in range(len(sensors)):
        print('Sensor found: %s' % sensors[index])


def on_sensor_state_changed(sensor, state):
    print('Sensor {0} is {1}'.format(sensor.name, state))


def on_battery_changed(sensor, battery):
    print('Battery: {0}'.format(battery))


def on_signal_received(sensor, data):
    raw_channels = []
    for sample in data:
        left_bipolar = sample.T3-sample.O1
        right_bipolar = sample.T4-sample.O2
        raw_channels.append(support_classes.RawChannels(left_bipolar, right_bipolar))

    math.push_data(raw_channels)
    math.process_data_arr()
    print("Artifacted: both sides - {0}, sequence - {1}".format(math.is_both_sides_artifacted(), math.is_artifacted_sequence()))
    if not math.calibration_finished():
        print("Calibration percents: {0}".format(math.get_calibration_percents()))
    else:
        mental_data = math.read_mental_data_arr()
        if len(mental_data) > 0:
            print("Mental data: {0}".format(mental_data))
        spectral_data = math.read_spectral_data_percents_arr()
        if len(spectral_data) > 0:
            print("Spectral data: {0}".format(spectral_data))


def on_resist_received(sensor, data):
    print("O1 resist is normal: {0}. Current O1 resist {1}".format(data.O1 < 2000000, data.O1))
    print("O2 resist is normal: {0}. Current O2 resist {1}".format(data.O2 < 2000000, data.O2))
    print("T3 resist is normal: {0}. Current T3 resist {1}".format(data.T3 < 2000000, data.T3))
    print("T4 resist is normal: {0}. Current T4 resist {1}".format(data.T4 < 2000000, data.T4))


try:
    scanner = Scanner([SensorFamily.LEHeadband])

    scanner.sensorsChanged = sensor_found
    scanner.start()
    print("Starting search for 25 sec...")
    sleep(25)
    scanner.stop()

    sensorsInfo = scanner.sensors()
    for i in range(len(sensorsInfo)):

        # connect to device
        current_sensor_info = sensorsInfo[i]
        # create_sensor is a blocking method, so its execution should preferably be placed in a separate thread 
        sensor = scanner.create_sensor(current_sensor_info)
        print("Current connected device {0}".format(current_sensor_info))

        # subscribe to events
        sensor.sensorStateChanged = on_sensor_state_changed
        sensor.batteryChanged = on_battery_changed
        sensor.signalDataReceived = on_signal_received
        sensor.resistDataReceived = on_resist_received

        # check resistance
        sensor.exec_command(SensorCommand.StartResist)
        print("Start resistance")
        sleep(20)
        sensor.exec_command(SensorCommand.StopResist)
        print("Stop resistance")

        # init emotions lib
        calibration_length = 6
        nwins_skip_after_artifact = 10

        mls = lib_settings.MathLibSetting(sampling_rate=250,
                                          process_win_freq=25,
                                          n_first_sec_skipped=4,
                                          fft_window=1000,
                                          bipolar_mode=True,
                                          squared_spectrum=True,
                                          channels_number=4,
                                          channel_for_analysis=0)
        ads = lib_settings.ArtifactDetectSetting(art_bord=110,
                                                 allowed_percent_artpoints=70,
                                                 raw_betap_limit=800_000,
                                                 global_artwin_sec=4,
                                                 num_wins_for_quality_avg=125,
                                                 hamming_win_spectrum=True,
                                                 hanning_win_spectrum=False,
                                                 total_pow_border=400_000_000,
                                                 spect_art_by_totalp=True)
        sads = lib_settings.ShortArtifactDetectSetting(ampl_art_detect_win_size=200,
                                                       ampl_art_zerod_area=200,
                                                       ampl_art_extremum_border=25)
        mss = lib_settings.MentalAndSpectralSetting(n_sec_for_averaging=2,
                                                    n_sec_for_instant_estimation=4)

        math = emotional_math.EmotionalMath(mls, ads, sads, mss)
        math.set_calibration_length(calibration_length)
        math.set_mental_estimation_mode(False)
        math.set_skip_wins_after_artifact(nwins_skip_after_artifact)
        math.set_zero_spect_waves(True, 0, 1, 1, 1, 0)
        math.set_spect_normalization_by_bands_width(True)

        # start calculations
        if sensor.is_supported_command(SensorCommand.StartSignal):
            sensor.exec_command(SensorCommand.StartSignal)
            print("Start signal")
            # start emotions calibration
            math.start_calibration()
            sleep(120)
            sensor.exec_command(SensorCommand.StopSignal)
            print("Stop signal")

        sensor.disconnect()
        print("Disconnect from sensor")
        del sensor
        del math

    del scanner
    print('Remove scanner')
except Exception as err:
    print(err)