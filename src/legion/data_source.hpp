//
//  data_source.hpp
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef data_source_hpp
#define data_source_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "robust_task.hpp"


class DataSource : public RobustTask {
  
public:
  DataSource();
  virtual ~DataSource();
  
private:
};


#endif /* data_source_hpp */
