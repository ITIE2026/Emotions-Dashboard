#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <thread>

#include "CCapsuleAPI.h"

using namespace std::chrono_literals;

// objects for establishing a connection with the device and capsule
clCNFBCalibrator calibrator = nullptr;
clCDeviceLocator locator = nullptr;
clCDevice device = nullptr;

clCNFB nfb = nullptr;
clCProductivity productivity = nullptr;
clCCardio cardio = nullptr;
clCMEMS mems = nullptr;
clCPhysiologicalStates ps = nullptr;
clCEmotions emotions = nullptr;

std::atomic_bool stopRequested = false;

void onDeviceModeSwitched(clCDevice, clCDevice_Mode mode) noexcept {
    std::cout << "Device mode changed: " << mode << std::endl;
}

void onDeviceResistanceUpdate(clCDevice, clCResistance resist) noexcept {
    std::cout << "Resistances: " << clCResistance_GetCount(resist) << std::endl;
    for (int32_t i = 0; i < clCResistance_GetCount(resist); ++i) {
        const char* channel = clCResistance_GetChannelName(resist, i);
        std::cout << "\t " << channel << " = " << clCResistance_GetValue(resist, i) << '\n';
    }
}

void onDeviceBatteryChargeUpdate(clCDevice, uint8_t batteryCharge) noexcept {
    std::cout << "Battery charge: " << static_cast<int>(batteryCharge) << '\n';
}

void onUpdateUserState(clCNFB, const clCNFB_UserState* userState) noexcept {
    // Getting NFB user data
    // if artifacts or weak resistance on the electrodes are observed,
    // the data will not be changed
    std::cout << "NFB update state: alpha = " << userState->alpha << " , beta = " << userState->beta << " , theta = " << userState->theta << std::endl;
}

void onNFBErrorEvent(clCNFB, const char* error) noexcept {
    std::cerr << "NFB error: " << error << std::endl;
}

void onProductivityBaselineUpdate(clCProductivity, const clCProductivity_Baselines* baselines) noexcept {
    std::cout << "Productivity baselines update:\n"
              << "\tTimestamp: " << baselines->timestampMilli << '\n'
              << "\tGravity: " << baselines->gravity << '\n'
              << "\tProductivity: " << baselines->productivity << '\n'
              << "\tFatigue: " << baselines->fatigue << '\n'
              << "\tReverse Fatigue: " << baselines->reverseFatigue << '\n'
              << "\tRelaxation: " << baselines->relaxation << '\n'
              << "\tConcentration: " << baselines->concentration << std::endl;
}

void onProductivityMetricsUpdate(clCProductivity, const clCProductivity_Metrics* metrics) noexcept {
    std::cout << "Productivity score update: " << metrics->currentValue << std::endl;
}

void onProductivityIndexesUpdate(clCProductivity, const clCProductivity_Indexes* indexes) noexcept {
    std::cout << "Productivity indexes update:\n"
              << "\tStress: " << indexes->stress << '\n'
              << "\tRelaxation: " << indexes->relaxation << std::endl;
}

void onProductivityCalibrationProgress(clCProductivity, float progress) noexcept {
    std::cout << "Productivity baseline calibration progress: " << progress << std::endl;
}

void onProductivityIndividualNFBUpdate(clCProductivity) noexcept {
    std::cout << "Productivity individual nfb data has been updated" << std::endl;
}

void onCardioIndexesUpdate(clCCardio, const clCCardio_Data* data) noexcept {
    std::cout << "Cardio indexes update: (has artifacts: " << data->hasArtifacts
              << "), Kaplan's index " << data->kaplanIndex << ", HR " << data->heartRate
              << ", stress index " << data->stressIndex << ", skin contact " << data->skinContact
              << ", motion artifacts " << data->motionArtifacts << ", metrics available " << data->metricsAvailable << std::endl;
}

void onMEMSUpdate(clCMEMS, clCMEMSTimedData data) noexcept {
    const int32_t count = clCMEMSTimedData_GetCount(data);
    std::cout << "MEMS update: showing 1 of " << count << " values" << std::endl;
    const clCPoint3d accelerometer = clCMEMSTimedData_GetAccelerometer(data, 0);
    const clCPoint3d gyroscope = clCMEMSTimedData_GetGyroscope(data, 0);
    const auto timestamp = clCMEMSTimedData_GetTimestampMilli(data, 0);
    std::cout << "\taccelerometer: " << accelerometer.x << ", "
              << accelerometer.y << ", " << accelerometer.z << std::endl;
    std::cout << "\tgyroscope: " << gyroscope.x << ", "
              << gyroscope.y << ", " << gyroscope.z << std::endl;
    std::cout << "\ttime: " << std::to_string(timestamp) << std::endl;
}

void onPhysiologicalStatesCalibrated(clCPhysiologicalStates, const clCPhysiologicalStates_Baselines* baselines) noexcept {
    std::cout << "Physiological states baselines calibrated:\n"
              << "\tTimestamp: " << baselines->timestampMilli << '\n'
              << "\tAlpha: " << baselines->alpha << '\n'
              << "\tBeta: " << baselines->beta << '\n'
              << "\tConcentration: " << baselines->concentration << '\n'
              << "\tAlpha Gravity: " << baselines->alphaGravity << '\n'
              << "\tBeta Gravity: " << baselines->betaGravity << std::endl;
}

void onPhysiologicalStatesUpdate(clCPhysiologicalStates, const clCPhysiologicalStates_Value* value) noexcept {
    std::cout << "Physiological states update:\n"
              << "\tTimestamp: " << value->timestampMilli << '\n'
              << "\tRelaxation: " << value->relaxation << '\n'
              << "\tFatigue: " << value->fatigue << '\n'
              << "\tNone: " << value->none << '\n'
              << "\tConcentration: " << value->concentration << '\n'
              << "\tInvolvement: " << value->involvement << '\n'
              << "\tStress: " << value->stress << '\n'
              << "\tNfb Artifacts: " << value->nfbArtifacts << '\n'
              << "\tCardio Artifacts: " << value->cardioArtifacts << std::endl;
}

void onPhysiologicalStatesIndividualNFBUpdate(clCPhysiologicalStates) noexcept {
    std::cout << "Physiological states individual nfb data has been updated" << std::endl;
}

void onEmotionalStatesUpdate(clCEmotions, const clCEmotions_States* states) noexcept {
    std::cout << "Emotional states update:\n"
              << "\tAttention: " << states->attention << '\n'
              << "\tRelaxation: " << states->relaxation << '\n'
              << "\tCognitive Load: " << states->cognitiveLoad << '\n'
              << "\tCognitive Control: " << states->cognitiveControl << '\n'
              << "\tSelfControl: " << states->selfControl << std::endl;
}

void onCalibrated(clCNFBCalibrator, const clCIndividualNFBData* data) noexcept {
    if (data == nullptr || data->failReason != clC_IndividualNFBCalibrationFailReason_None) {
        std::cerr << "Calibration failed";
        switch (data->failReason) {
        case clC_IndividualNFBCalibrationFailReason_TooManyArtifacts:
            std::cerr << ": Too many artifacts";
            break;
        case clC_IndividualNFBCalibrationFailReason_PeakIsABorder:
            std::cerr << ": Alpha peak matches one of the alpha range borders";
            break;
        default:
            std::cerr << ": Reason unknown";
        }
    }
    std::cout << "IAF:" << data->individualFrequency << std::endl;

    clCProductivity_StartBaselineCalibration(productivity);
}

void onDeviceError(clCDevice, const char* error) noexcept {
    std::cerr << "Device error: " << error << std::endl;
}

void onConnectionStatusChanged(clCDevice, clCDevice_ConnectionStatus state) noexcept {
    if (state != clCDevice_ConnectionState_Connected) {
        std::cout << "Device disconnected" << std::endl;
        stopRequested = true;
        return;
    }
    std::cout << "Device connected" << std::endl;

    clCError error;
    clCDevice_ChannelNames channelNames = clCDevice_GetChannelNames(device, &error);
    const auto channelsCount = clCDevice_ChannelNames_GetChannelsCount(channelNames, &error);
    std::cout << "Device has " << channelsCount << " channels: [";
    for (int32_t i = 0; i < channelsCount; ++i) {
        std::cout << clCDevice_ChannelNames_GetChannelNameByIndex(channelNames, i, &error) << ", ";
    }
    std::cout << "\b\b]" << std::endl;
    for (int32_t i = 0; i < channelsCount; ++i) {
        const char* channel = clCDevice_ChannelNames_GetChannelNameByIndex(channelNames, i, &error);
        const auto index = clCDevice_ChannelNames_GetChannelIndexByName(channelNames, channel, &error);
        std::cout << "\tChannel " << channel << " has index " << index << std::endl;
    }

    std::cout << "EEG sample rate: " << clCDevice_GetEEGSampleRate(device, nullptr) << '\n'
              << "PPG sample rate: " << clCDevice_GetPPGSampleRate(device, nullptr) << '\n'
              << "MEMS sample rate: " << clCDevice_GetMEMSSampleRate(device, nullptr) << '\n'
              << "PPG IR amplitude: " << clCDevice_GetPPGIrAmplitude(device, nullptr) << '\n'
              << "PPG red amplitude: " << clCDevice_GetPPGRedAmplitude(device, nullptr) << std::endl;

    clCDevice_Start(device, &error);

    if (ps != nullptr) {
        clCPhysiologicalStates_StartBaselineCalibration(ps);
    }

    std::cout << "Calibration started\n"
              << "Close your eyes for 30 seconds" << std::endl;
    clCNFBCalibrator_CalibrateIndividualNFBQuick(calibrator, &error);
    if (!error.success) {
        std::cerr << error.message << std::endl;
        stopRequested = true;
    }
}

void onDeviceList(clCDeviceLocator locator, clCDeviceInfoList devices, clCDeviceLocator_FailReason failReason) noexcept {
    if (device != nullptr) {
        return;
    }

    if (failReason != clCDeviceLocator_FailReason_OK) {
        switch (failReason) {
        case clCDeviceLocator_FailReason_BluetoothDisabled:
            std::cerr << "Bluetooth adapter not found or disabled";
            break;
        default:
            std::cerr << "Unknown error occurred";
        }
        std::cerr << ". Exiting..." << std::endl;
        stopRequested = true;
        return;
    }

    clCError error;
    if (clCDeviceInfoList_GetCount(devices, &error) == 0) {
        std::cerr << "Empty device list. Exiting..." << std::endl;
        stopRequested = true;
        return;
    }

    // print information about all found devices
    const int32_t count = clCDeviceInfoList_GetCount(devices, &error);
    std::cout << "Devices: " << count << std::endl;
    for (int i = 0; i < count; ++i) {
        clCDeviceInfo deviceDescriptor = clCDeviceInfoList_GetDeviceInfo(devices, i, &error);
        std::cout << "\t " << clCDeviceInfo_GetSerial(deviceDescriptor) << std::endl;
    }

    // select device and connect
    clCDeviceInfo deviceDescriptor = clCDeviceInfoList_GetDeviceInfo(devices, 0, &error);
    const char* deviceID = clCDeviceInfo_GetSerial(deviceDescriptor);
    device = clCDeviceLocator_CreateDevice(locator, deviceID, &error);
    if (device == nullptr) {
        std::cerr << "Failed to create device. Exiting..." << std::endl;
        stopRequested = true;
        return;
    }

    clCDevice_SetOnModeSwitchedEvent(device, onDeviceModeSwitched);
    clCDevice_SetOnResistanceUpdateEvent(device, onDeviceResistanceUpdate);
    clCDevice_SetOnBatteryChargeUpdateEvent(device, onDeviceBatteryChargeUpdate);
    clCDevice_SetOnConnectionStatusChangedEvent(device, onConnectionStatusChanged);
    clCDevice_SetOnErrorEvent(device, onDeviceError);

    calibrator = clCNFBCalibrator_CreateOrGet(device);
    clCNFBCalibrator_SetOnCalibratedEvent(calibrator, onCalibrated);

    nfb = clCNFB_Create(device, &error);
    if (nfb == nullptr) {
        std::cerr << error.message << std::endl;
        stopRequested = true;
        return;
    }
    clCNFB_SetOnUserStateChangedEvent(nfb, onUpdateUserState);
    clCNFB_SetOnErrorEvent(nfb, onNFBErrorEvent);

    cardio = clCCardio_Create(device, &error);
    if (cardio == nullptr) {
        if (error.code == clCError_ModuleIsNotSupported) {
            std::cout << error.message << std::endl;
        } else {
            std::cerr << error.message << std::endl;
            stopRequested = true;
            return;
        }
    }
    if (cardio != nullptr) {
        clCCardio_SetOnIndexesUpdateEvent(cardio, onCardioIndexesUpdate, &error);
    }

    mems = clCMEMS_Create(device, &error);
    if (mems == nullptr) {
        if (error.code == clCError_ModuleIsNotSupported) {
            std::cout << error.message << std::endl;
        } else {
            std::cerr << error.message << std::endl;
            stopRequested = true;
            return;
        }
    }
    if (mems != nullptr) {
        clCMEMS_SetOnMEMSTimedDataUpdateEvent(mems, onMEMSUpdate, &error);
    }

    productivity = clCProductivity_Create(device, &error);
    if (productivity == nullptr) {
        std::cerr << error.message << std::endl;
        stopRequested = true;
        return;
    }

    clCProductivity_SetOnBaselineUpdateEvent(productivity, onProductivityBaselineUpdate);
    clCProductivity_SetOnMetricsUpdateEvent(productivity, onProductivityMetricsUpdate);
    clCProductivity_SetOnIndexesUpdateEvent(productivity, onProductivityIndexesUpdate);
    clCProductivity_SetOnCalibrationProgressUpdateEvent(productivity, onProductivityCalibrationProgress);
    clCProductivity_SetOnIndividualNFBUpdateEvent(productivity, onProductivityIndividualNFBUpdate);

    ps = clCPhysiologicalStates_Create(device, &error);
    if (ps == nullptr) {
        if (error.code == clCError_ModuleIsNotSupported) {
            std::cout << error.message << std::endl;
        } else {
            std::cerr << error.message << std::endl;
            stopRequested = true;
            return;
        }
    }
    if (ps != nullptr) {
        clCPhysiologicalStates_SetOnCalibratedEvent(ps, onPhysiologicalStatesCalibrated, &error);
        clCPhysiologicalStates_SetOnStatesUpdateEvent(ps, onPhysiologicalStatesUpdate, &error);
        clCPhysiologicalStates_SetOnIndividualNFBUpdateEvent(ps, onPhysiologicalStatesIndividualNFBUpdate, &error);
    }

    emotions = clCEmotions_Create(device, &error);
    if (!error.success) {
        std::cerr << error.message << std::endl;
        stopRequested = true;
        return;
    }
    clCEmotions_SetOnEmotionalStatesUpdateEvent(emotions, onEmotionalStatesUpdate);

    clCDevice_Connect(device, true, &error);
}

void Cleanup() {
    calibrator = nullptr;
    clCError error;
    if (device) {
        clCDevice_Stop(device, &error);
        clCDevice_Disconnect(device, &error);
        clCDevice_Release(device);
        device = nullptr;
    }
    if (locator) {
        clCDeviceLocator_Destroy(locator);
    }
    locator = nullptr;
    std::cout << "End work" << std::endl;
}

void SignalHandler(int signal) {
    if (signal == SIGINT) {
        std::cout << "\nCtrl + C pressed. Exiting gracefully...\n";
        stopRequested = true;
    }
}

int main() {
    clCError error;
    std::signal(SIGINT, SignalHandler);

    std::cout << "To quit the example press Ctrl + C" << std::endl;

    // Getting the version of the library
    {
        const char* strPtr = clCCapsule_GetVersionString();
        std::cout << "Version of the library: " << strPtr << std::endl;
    }

    clCDeviceLocator locator = clCDeviceLocator_Create(&error);
    clCDeviceLocator_SetOnDeviceListEvent(locator, onDeviceList);
    clCDeviceLocator_RequestDevices(locator, clCDeviceType_Headband, 15, &error);

    while (!stopRequested) {
        std::this_thread::sleep_for(40ms);
    }

    Cleanup();

    return 0;
}
