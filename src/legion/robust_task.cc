//
//  robust_task.cc
//
//
//  Created by Heirich, Alan on 5/4/18.
//

#include "robust_task.hpp"
#include "control_store.hpp"

RobustTask::RobustTask() {
}

RobustTask::~RobustTask() {
}

std::string RobustTask::key(const Task* task) {
  char buffer[256];
  sprintf(buffer, "_%s_%lld", task->get_task_name(), task->get_unique_id());
  return std::string(buffer);
}


