# Windows
To build with CMake use the following:
```bash
cd Example/Win
cmake -S . -B ./build -G "Visual Studio 17 2022" -A x64
cmake --build ./build --config Release
```

# MacOS
You may be prompted to grant permissions for unknown library `libCapsuleClient.dylib`.

This is a normal behavior, you can sign your app later.

For Apple Silicon CPU based devices run this command:
```zsh
arch -x86_64 zsh
```
and then proceed as usual.

To build with CMake use the following:
```bash
cd Example/Mac
cmake -S . -L ./build/libCapsuleClient.dylib -B ./build -G  "Xcode"
cmake --build ./build --config Release
```

# Description

Above-mentioned commands will build several example executables. Here's their description and usage. 

## Client Example

This example shows how to use basic features of Capsule C API.

### Usage

To run this example, `cd` to the directory, where examples were built and run the following command:

```bash
./CapsuleClientExample
```

To **quit** the example press `Ctrl + C`.

## Raw Signal Example

This example shows how to get raw signal data (EEG, PPG and MEMS) from a device using C API.

### Usage

To run this example, `cd` to the directory, where examples were built and run the following command:

```bash
./CapsuleSignalExample --csv=[true/false]
```

This example accepts an optional argument:

- `--csv=<BOOL>` - write signal data to a csv file. It accepts `[true, on, 1]` for **true** and `[false, off, 0]` for **false**

You can omit the argument. In that case the program will ask you to choose the setting during execution.

To **quit** the example press `Ctrl + C`.