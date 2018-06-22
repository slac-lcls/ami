//
//  robustness_monitor.hpp
//  
//
//  Created by Heirich, Alan on 5/3/18.
//

#ifndef robustness_monitor_hpp
#define robustness_monitor_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "robust_task.hpp"

class RobustnessMonitor : public RobustTask {
  
public:
  RobustnessMonitor();
  virtual ~RobustnessMonitor();
  static void robustness_monitor_task(const Task* task,
                                      const std::vector<PhysicalRegion> &regions,
                                      Context ctx, Runtime* runtime);
private:
};

#endif /* robustness_monitor_hpp */
