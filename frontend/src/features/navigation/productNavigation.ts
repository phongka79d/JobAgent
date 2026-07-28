export type ProductDestination = 'overview' | 'saved-jobs' | 'tailored-cvs';

export type ProductDestinationDefinition = {
  readonly id: ProductDestination;
  readonly label: string;
  readonly icon: 'info' | 'copy' | 'clock';
};

export const PRODUCT_DESTINATIONS = [
  {id: 'overview', label: 'Overview', icon: 'info'},
  {id: 'saved-jobs', label: 'Saved Jobs', icon: 'copy'},
  {id: 'tailored-cvs', label: 'Tailored CVs', icon: 'clock'},
] as const satisfies readonly ProductDestinationDefinition[];
