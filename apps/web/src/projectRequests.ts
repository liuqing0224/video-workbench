// A response may update the workspace only while its selection and request are current.
export class ProjectRequestGuard {
  projectId: string | undefined;
  private generation = 0;
  private sequence = 0;
  select(id: string) {
    this.projectId = id;
    this.generation++;
  }
  begin(id: string | undefined) {
    const generation = this.generation;
    const sequence = ++this.sequence;
    return () => this.projectId === id && this.generation === generation && this.sequence === sequence;
  }
}
