//
//  file_data_source.hpp
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef file_data_source_hpp
#define file_data_source_hpp

#include <iostream>
#include <fstream>
#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "data_source.hpp"


class FileDataSource : public DataSource {
  
public:
  FileDataSource();
  virtual ~FileDataSource();
  void selectFileDataSource(std::string filePathBase);
  static void task(const Task* task,
                   const std::vector<PhysicalRegion> &regions,
                   Context ctx, Runtime* runtime);
private:
  static bool telemetryDataExists();
  static void writeTelemetryDataToRegion();
  static void openFileDataSource(std::string base);
  static std::string dataSourceFileName(std::string base);

  static std::string mFilePathBase;
  static std::ifstream mInputFile;
  static bool mOpenedDataSource;
  static bool mSelectedDataSource;
};


#endif /* file_data_source_hpp */
