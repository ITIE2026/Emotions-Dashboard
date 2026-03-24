#include <atomic>
#include <chrono>
#include <csignal>
#include <fstream>
#include <iostream>
#include <thread>

#include "ExampleUtils.hpp"

#include "CCardio.h"
#include "CDevice.h"
#include "CMEMS.h"
#include "CMEMSTimedData.h"
#include "CPPGTimedData.h"

using namespace std::chrono_literals;

clCDeviceLocator locator = nullptr;
clCDevice device = nullptr;
clCCardio cardio = nullptr;
clCMEMS mems = nullptr;

bool writeCsv = false;

std::atomic_bool stopRequested = false;

std::ofstream ppgStream;
void onPPGData(clCCardio, clCPPGTimedData ppgData) noexcept {
    const int32_t count = clCPPGTimedData_GetCount(ppgData);
    std::cout << "PPG raw data received " << count << " samples" << std::endl;

    if (!writeCsv || !ppgStream.is_open()) {
        return;
    }
    for (int32_t i = 0; i < count; ++i) {
        ppgStream << clCPPGTimedData_GetTimestampMilli(ppgData, i) << ',' << clCPPGTimedData_GetValue(ppgData, i) << std::endl;
    }
}

std::ofstream memsStream;
void onMEMSData(clCMEMS, clCMEMSTimedData memsData) noexcept {
    const int32_t count = clCMEMSTimedData_GetCount(memsData);
    std::cout << "MEMS raw data received " << count << " samples" << std::endl;

    if (!writeCsv || !memsStream.is_open()) {
        return;
    }
    for (int32_t i = 0; i < count; ++i) {
        const auto acc = clCMEMSTimedData_GetAccelerometer(memsData, i);
        const auto gyro = clCMEMSTimedData_GetGyroscope(memsData, i);
        memsStream << clCMEMSTimedData_GetTimestampMilli(memsData, i) << ','
                   << acc.x << ',' << acc.y << ',' << acc.z << ','
                   << gyro.x << ',' << gyro.y << ',' << gyro.z << std::endl;
    }
}

std::ofstream eegStream;
std::ofstream processedEegStream;
void onEEGData(clCDevice, clCEEGTimedData eegData) noexcept {
    const int32_t samples = clCEEGTimedData_GetSamplesCount(eegData, nullptr);
    const int32_t channels = clCEEGTimedData_GetChannelsCount(eegData, nullptr);
    std::cout << "Raw EEG data received " << channels << " channels and " << samples << " samples" << std::endl;
    std::cout << "Processed EEG data received " << channels << " channels and " << samples << " samples" << std::endl;

    if (!writeCsv || !eegStream.is_open()) {
        return;
    }
    for (int32_t i = 0; i < samples; ++i) {
        eegStream << clCEEGTimedData_GetTimestampMilli(eegData, i, nullptr) << ',';
        for (int32_t j = 0; j < channels; ++j) {
            eegStream << clCEEGTimedData_GetRawValue(eegData, j, i, nullptr);
            if (j == channels - 1) {
                eegStream << std::endl;
            } else {
                eegStream << ',';
            }
        }
    }

    if (!processedEegStream.is_open()) {
        return;
    }

    for (int32_t i = 0; i < samples; ++i) {
        processedEegStream << clCEEGTimedData_GetTimestampMilli(eegData, i, nullptr) << ',';
        for (int32_t j = 0; j < channels; ++j) {
            processedEegStream << clCEEGTimedData_GetProcessedValue(eegData, j, i, nullptr) << ',';

            if (j == channels - 1) {
                processedEegStream << std::endl;
            } else {
                processedEegStream << ',';
            }
        }
    }
}

std::ofstream artifactsStream;
void onEEGArtifacts(clCDevice, clCEEGArtifacts eegArtifacts) noexcept {
    const int32_t channels = clCEEGArtifacts_GetChannelsCount(eegArtifacts, nullptr);
    std::cout << "EEG artifacts received " << channels << " channels" << std::endl;

    if (!writeCsv || !artifactsStream.is_open()) {
        return;
    }

    artifactsStream << clCEEGArtifacts_GetTimestampMilli(eegArtifacts, nullptr) << ',';
    for (int32_t i = 0; i < channels; ++i) {
        artifactsStream << static_cast<int>(clCEEGArtifacts_GetArtifactByChannel(eegArtifacts, i, nullptr)) << ','
                        << clCEEGArtifacts_GetEEGQuality(eegArtifacts, i, nullptr);
        if (i == channels - 1) {
            artifactsStream << std::endl;
        } else {
            artifactsStream << ',';
        }
    }
}

void onPSDData(clCDevice, clCPSDData psdData) noexcept {
    const int32_t channels = clCPSDData_GetChannelsCount(psdData, nullptr);
    const int32_t frequencies = clCPSDData_GetFrequenciesCount(psdData, nullptr);
    std::cout << "PSD data received " << channels << " channels and " << frequencies << " frequencies" << std::endl;
}

void onConnectionStatusChanged(clCDevice, clCDevice_ConnectionStatus state) noexcept {
    // status of the device changed
    if (state != clCDevice_ConnectionState_Connected) {
        std::cout << "Device disconnected" << std::endl;
        stopRequested = true;
        return;
    }
    std::cout << "Device connected" << std::endl;

    clCDevice_ChannelNames channelNames = clCDevice_GetChannelNames(device, nullptr);
    const auto channelsCount = clCDevice_ChannelNames_GetChannelsCount(channelNames, nullptr);
    if (writeCsv) {
        ppgStream.open("device_ppg.csv");
        ppgStream << "timestamp,value\n";
        memsStream.open("device_mems.csv");
        memsStream << "timestamp,ax,ay,az,gx,gy,gz\n";
        eegStream.open("device_eeg.csv");
        eegStream << "timestamp,";
        processedEegStream.open("processed_eeg.csv");
        processedEegStream << "timestamp,";
        artifactsStream.open("eeg_artifacts.csv");
        artifactsStream << "timestamp,";

        for (int32_t i = 0; i < channelsCount; ++i) {
            const char* channelName = clCDevice_ChannelNames_GetChannelNameByIndex(channelNames, i, nullptr);
            std::cout << "\tChannel " << channelName
                      << " has index " << clCDevice_ChannelNames_GetChannelIndexByName(channelNames, channelName, nullptr) << std::endl;
            eegStream << channelName;
            processedEegStream << channelName;

            artifactsStream << "artifact_" << i << ',' << "quality_" << i;
            if (i == channelsCount - 1) {
                eegStream << std::endl;
                processedEegStream << std::endl;
                artifactsStream << std::endl;
            } else {
                eegStream << ',';
                processedEegStream << ',';
                artifactsStream << ',';
            }
        }
    }

    std::cout << "Device has " << channelsCount << " channels: [";
    for (int32_t i = 0; i < channelsCount; ++i) {
        const char* channelName = clCDevice_ChannelNames_GetChannelNameByIndex(channelNames, i, nullptr);
        std::cout << channelName << ", ";
    }
    std::cout << "\b\b]" << std::endl;

    clCDevice_Start(device, nullptr);
}

void onDeviceError(clCDevice, const char* error) noexcept {
    std::cerr << "Device error: " << error << std::endl;
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
    const char* deviceSerial = clCDeviceInfo_GetSerial(deviceDescriptor);
    device = clCDeviceLocator_CreateDevice(locator, deviceSerial, &error);
    if (device == nullptr) {
        std::cerr << "Failed to create device. Exiting..." << std::endl;
        stopRequested = true;
        return;
    }

    clCDevice_SetOnConnectionStatusChangedEvent(device, onConnectionStatusChanged);
    clCDevice_SetOnErrorEvent(device, onDeviceError);

    cardio = clCCardio_Create(device, nullptr);
    mems = clCMEMS_Create(device, nullptr);
    clCCardio_SetOnPPGDataEvent(cardio, onPPGData, nullptr);
    clCMEMS_SetOnMEMSTimedDataUpdateEvent(mems, onMEMSData, nullptr);

    clCDevice_SetOnEEGDataEvent(device, onEEGData);
    clCDevice_SetOnEEGArtifactsEvent(device, onEEGArtifacts);
    clCDevice_SetOnPSDDataEvent(device, onPSDData);

    clCDevice_Connect(device, true, nullptr);
}

void Cleanup() {
    if (device) {
        clCDevice_Disconnect(device, nullptr);
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

int main(int argc, char* argv[]) {
    std::signal(SIGINT, SignalHandler);

    parseArgs(argc, argv, nullptr, &writeCsv);

    std::cout << std::boolalpha << "Write to CSV: " << writeCsv << std::endl;
    std::cout << "To quit the example press Ctrl + C" << std::endl;

    // Getting the version of the library
    {
        const char* strPtr = clCCapsule_GetVersionString();
        std::cout << "Version of the library: " << strPtr << std::endl;
    }

    clCDeviceLocator locator = clCDeviceLocator_Create(nullptr);
    clCDeviceLocator_SetOnDeviceListEvent(locator, onDeviceList);
    clCDeviceLocator_RequestDevices(locator, clCDeviceType_Headband, 15, nullptr);

    while (!stopRequested) {
        std::this_thread::sleep_for(40ms);
    }

    Cleanup();

    return 0;
}
