/**
 * Datasource Context for JQ Backtest Workbench
 * Provides mock datasource information for independent development
 */
import React, { createContext, useContext, ReactNode } from 'react';

interface DatasourceContextType {
  datasource: {
    id: string;
    name: string;
    type: string;
  } | null;
}

const DatasourceContext = createContext<DatasourceContextType>({
  datasource: null,
});

export const useDatasource = () => {
  const context = useContext(DatasourceContext);
  return context;
};

interface DatasourceProviderProps {
  children: ReactNode;
}

export const DatasourceProvider: React.FC<DatasourceProviderProps> = ({ children }) => {
  // Mock datasource for independent development
  const datasource = {
    id: 'mock-datasource',
    name: 'CSV数据源',
    type: 'csv',
  };

  return (
    <DatasourceContext.Provider value={{ datasource }}>
      {children}
    </DatasourceContext.Provider>
  );
};

export default DatasourceContext;
