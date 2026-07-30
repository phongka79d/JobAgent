import {useEffect} from 'react';

export function useWorkspaceLifecycle(reload: () => Promise<void>): void {
  useEffect(() => {
    const onPageShow = () => {
      void reload();
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, [reload]);
}
