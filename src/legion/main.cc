//
//  main.cpp
//  
//
//  Created by Heirich, Alan on 5/15/18.
//

#include <stdio.h>

#include "toplevel.hpp"


static void preregisterTasks() {
  TaskVariantRegistrar registrar(TopLevelTask::TOP_LEVEL_TASK, "top_level_task");
  Runtime::preregister_task_variant<TopLevelTask::top_level_task>(registrar, "top_level_task");
  registrar.set_leaf();
  Runtime::preregister_task_variant<Worker::worker_task>(registrar, "worker_task", TopLevelTask::WORKER_TASK);
  registrar.set_leaf();
  Runtime::preregister_task_variant<Collector::collector_task>(registrar, "collector_task", TopLevelTask::COLLECTOR_TASK);
  registrar.set_leaf();
  Runtime::preregister_task_variant<SharedMemoryDataSource::task>(registrar, "shared_memory_data_source_task", TopLevelTask::SHARED_MEMORY_DATA_SOURCE_TASK);
  registrar.set_leaf();
  Runtime::preregister_task_variant<FileDataSource::task>(registrar, "file_data_source_task", TopLevelTask::FILE_DATA_SOURCE_TASK);
  registrar.set_leaf();
  Runtime::preregister_task_variant<GraphManager::graph_manager_task>(registrar, "graph_manager_task", TopLevelTask::GRAPH_MANAGER_TASK);
  registrar.set_leaf();
  Runtime::preregister_task_variant<RobustnessMonitor::robustness_monitor_task>(registrar, "robustness_monitor_task", TopLevelTask::ROBUSTNESS_MONITOR_TASK);
}




int main(int argc, char *argv[]) {
  Runtime::set_top_level_task_id(TopLevelTask::TOP_LEVEL_TASK);
  preregisterTasks();
  return Runtime::start(argc, argv);
}
