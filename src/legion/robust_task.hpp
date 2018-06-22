//
//  robust_task.hpp
//
//
//  Created by Heirich, Alan on 5/4/18.
//

#ifndef robust_task_hpp
#define robust_task_hpp

#include <stdio.h>

#include "legion.h"
using namespace Legion;

#include "control_store.hpp"


class RobustTask {
  
public:
  RobustTask();
  virtual ~RobustTask();
  
private:
  static std::string key(const Task* task);
};


#endif /* robust_task_hpp */

