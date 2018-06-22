//
//  worker.hpp
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef worker_hpp
#define worker_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "robust_task.hpp"

class Worker : public RobustTask {
  
public:
  Worker();
  virtual ~Worker();
  static void worker_task(const Task* task,
                          const std::vector<PhysicalRegion> &regions,
                          Context ctx, Runtime* runtime);
  
private:
};

#endif /* worker_hpp */
