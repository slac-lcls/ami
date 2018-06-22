//
//  file_data_source.cc
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#include "file_data_source.hpp"

// static data
std::string FileDataSource::mFilePathBase;
std::ifstream FileDataSource::mInputFile;
bool FileDataSource::mOpenedDataSource;
bool FileDataSource::mSelectedDataSource;


FileDataSource::FileDataSource() {
  mFilePathBase = nullptr;
  mOpenedDataSource = false;
  mSelectedDataSource = false;
}

FileDataSource::~FileDataSource() {
  if(mOpenedDataSource) {
    mInputFile.close();
  }
}


void FileDataSource::selectFileDataSource(std::string filePathBase) {
  mFilePathBase = filePathBase;
  mSelectedDataSource = true;
}


std::string FileDataSource::dataSourceFileName(std::string base) {
  return base + "_file.dat";//TODO base this on node id?
}


void FileDataSource::openFileDataSource(std::string base) {
  std::string filename = dataSourceFileName(base);
  mInputFile.open(filename, std::ios::in | std::ios::binary);
  mOpenedDataSource = true;
}


bool FileDataSource::telemetryDataExists() {
  if(mOpenedDataSource) {
    return true;//TODO
  }
  return false;
}


void FileDataSource::writeTelemetryDataToRegion() {
  // retrieve one frame of telemetry data
  // write it to the region
  // user code from commmon/ to access the data, other data source will write
}



void FileDataSource::task(const Task* task,
                          const std::vector<PhysicalRegion> &regions,
                          Context ctx, Runtime* runtime) {
  
  if(!mOpenedDataSource && mSelectedDataSource) {
    openFileDataSource(mFilePathBase);
  }
  
  if(telemetryDataExists()) {
    writeTelemetryDataToRegion();
  }
}



