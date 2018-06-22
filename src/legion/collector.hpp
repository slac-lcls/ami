//
//  collector.hpp
//  
//
//  Created by Heirich, Alan on 5/14/18.
//

#ifndef collector_hpp
#define collector_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "robust_task.hpp"

class Collector : public RobustTask {
  
public:
  Collector();
  virtual ~Collector();
  static void collector_task(const Task* task,
                             const std::vector<PhysicalRegion> &regions,
                             Context ctx, Runtime* runtime);
  
private:
};

#endif /* collector_hpp */
