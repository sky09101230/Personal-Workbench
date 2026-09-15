import { getTask, TaskSnapshot } from "./api";

export async function waitForTask(
  taskId: string,
  onUpdate: (task: TaskSnapshot) => void,
  intervalMs = 500,
): Promise<TaskSnapshot> {
  for (;;) {
    const task = await getTask(taskId);
    onUpdate(task);
    if (["succeeded", "failed", "cancelled"].includes(task.status)) return task;
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
}
